__author__ = '@paveres'
__channel__ = 'https://t.me/g_plugins'
__contact__ = 'https://t.me/paveres'
import copy, json, time
from .wallet import Wallet
from . import texts

class Aftercare:

    def __init__(self, store, engine, reviews=None):
        self.store = store
        self.engine = engine
        self.reviews = reviews
        self.wallet = Wallet(store)

    def review_known(self, o):
        if o['data'].get('review_seen') or (self.reviews and self.reviews.known(o['buyer'])):
            return True
        with self.store.tx() as db:
            return bool(db.execute("SELECT 1 FROM bonus_ledger WHERE buyer=? AND key LIKE 'review:%' LIMIT 1", (o['buyer'],)).fetchone())

    def completion(self, o):
        text = '💙【 Проверьте результат 】\n\nСкачайте архив и проверьте все TGS-файлы.\nЕсли всё верно, подтвердите выполнение заказа на FunPay:\nhttps://funpay.com/orders/' + o['id'] + '/'
        if o['data'].get('pack_urls'):
            text = text.replace('Скачайте архив и проверьте все TGS-файлы.', 'Откройте пак и проверьте все элементы.')
        if not self.review_known(o):
            text += '\n\nЗа честный отзыв, независимо от оценки, — +2 эмодзи на накопительный баланс.\nПолучить команды'
        return text

    def grant(self, oid, force_late=False):
        o = self.store.get(oid)
        if not o or o['data'].get('wallet_job') or o['data'].get('bonus_parent') or (o['stage'] in {'REFUNDED', 'CANCELLED'}):
            return None
        if not self.wallet.credit(o['buyer'], oid):
            return None
        self.store.patch(oid, review_seen=True, wallet_rewarded=True)
        self.store.event(o, 'wallet-review', '💙【 Рады видеть вас снова! 】\nСпасибо за отзыв. Начислено: +2 эмодзи.\nВаш бонусный баланс: ' + str(self.wallet.balance(o['buyer'])) + '\nБонусы не сгорают. !бонус — накопить или использовать.')
        return oid

    def notice(self, o):
        if not o['data'].get('bonus_notice_pending') or o['data'].get('bonus_parent'):
            return
        self.store.event(o, 'review-bonus', '💙【 Спасибо за отзыв! 】\n\nНачислено: +2 эмодзи бесплатно.\nТеперь доступно: ' + str(o['qty']) + ' эмодзи.\nВаш выбор, ник и оформление сохранены.\nДоберите 2 варианта из любой коллекции, затем продолжим.')
        self.engine.collections(o)
        o['data']['bonus_notice_pending'] = False
        self.store.save(o)

    def observe(self, o, remote, now=None):
        now = time.time() if now is None else now
        if remote.buyer_id != o['buyer']:
            return
        status = remote.status.name
        reviewed = bool(getattr(remote, 'review', None) and remote.review.stars)
        self.store.patch(o['id'], review_seen=bool(o['data'].get('review_seen') or reviewed), platform_confirmed=status == 'CLOSED', aftercare_checked=now)
        if status in {'REFUNDED', 'PARTIALLY_REFUNDED', 'CANCELLED'}:
            self.wallet.settle(o['id'], False)
            self.store.close(o['id'], 'REFUNDED' if 'REFUND' in status else 'CANCELLED')
            if o['data'].get('bonus_child'):
                self.store.close(o['data']['bonus_child'], 'CANCELLED')
            return
        if reviewed:
            if self.reviews:
                self.reviews.mark(o['buyer'], o['id'], int(remote.review.stars))
            self.grant(o['id'], force_late=status == 'CLOSED')
        o = self.store.get(o['id'])
        if status == 'CLOSED':
            if not o['data'].get('confirmed_thanked'):
                self.store.event(o, 'confirmed', '💙 Спасибо за подтверждение заказа' + (' и отзыв!' if reviewed else '!') + '\n' + ('Бонусные эмодзи доступны в этом чате.' if o['data'].get('bonus_child') else 'Будем рады видеть вас снова.'))
                self.store.patch(o['id'], confirmed_thanked=True)
            self.store.close(o['id'], 'CLOSED')
            return
        self.notice(o)
        o = self.store.get(o['id'])
        if o['stage'] != 'delivered':
            return
        with self.store.tx() as db:
            pending = db.execute("SELECT 1 FROM outbox WHERE oid=? AND state!='sent' AND key NOT LIKE '%:event:%' LIMIT 1", (o['id'],)).fetchone()
        if pending:
            return
        if o['data'].get('completion_version', 0) < 11:
            self.store.event(o, 'completion-v1.1', self.completion(o))
            self.store.patch(o['id'], completion_version=11, last_confirmation_contact=now, delivered_at=o['data'].get('delivered_at', now))
            return
        due = o['data'].get('last_confirmation_contact', o['data'].get('delivered_at', now)) + 86400
        if now < due:
            return
        text = '💙【 Заказ ожидает подтверждения 】\n\nЕсли вы скачали и проверили файлы, подтвердите выполнение заказа:\nhttps://funpay.com/orders/' + o['id'] + '/'
        if o['data'].get('pack_urls'):
            text = text.replace('Если вы скачали и проверили файлы', 'Если вы открыли и проверили пак')
        if not self.review_known(o):
            text += '\n\nЕсли хотите, оставьте честный отзыв. За любой отзыв — 2 эмодзи бесплатно, независимо от оценки.'
        self.store.event(o, 'reminder:' + str(int(due)), text)
        self.store.patch(o['id'], last_confirmation_contact=now)
