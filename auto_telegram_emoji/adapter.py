__author__ = '@justmeth'
__channel__ = 'https://t.me/g_plugins'
__contact__ = 'https://t.me/justmeth'
import json, logging, threading, time
from pathlib import Path
from decimal import Decimal
from . import SERVICE_ID, VERSION
from .catalog import Catalog
from .store import Store
from .render import Renderer
from .engine import Engine
from .transport import Transport
log = logging.getLogger('auto_telegram_emoji')
TERMINAL = {'CLOSED', 'REFUNDED', 'CANCELLED'}

class Adapter:

    def __init__(self, k, root):
        self.k = k
        self.root = Path(root)
        self.store = Store(self.root / 'data/orders.sqlite3')
        self.cat = Catalog(root)
        self.render = Renderer(root, self.cat)
        self.engine = Engine(self.store, self.cat, self.render)
        self.transport = Transport(k, self.store)
        self.engine.can_deliver = self.check_paid
        from .packs import Packs
        self.engine.packs = Packs(self.root, self.store)
        self.stop = threading.Event()
        self.started = False
        self.last_poll = 0
        from .queue import EmojiQueue
        self.queue = EmojiQueue(root)
        self.alerted = set()
        from concurrent.futures import ThreadPoolExecutor
        self.executor = ThreadPoolExecutor(max_workers=10, thread_name_prefix='emoji-buyer')
        self.futures = {}
        self.buyer_locks = {}
        self.ignored_orders = set()
        self.config_stamp = None
        from .input_gate import InputGate
        self.gate = InputGate(self.store)
        self.last_cleanup = 0
        from .aftercare import Aftercare
        from auto_telegram_emoji.reviews import ReviewRegistry
        self.lifecycle = Aftercare(self.store, self.engine, ReviewRegistry(root))
        from .public import Public
        self.public = Public(self)

    def allowed(self):
        from auto_telegram_emoji.platform import service_enabled
        return service_enabled(self.k, SERVICE_ID)

    def config(self):
        p = self.root / 'config/app.json'
        return json.loads(p.read_text()) if p.exists() else {'enabled': False, 'lots': {}}

    def start(self):
        if not self.started:
            self.started = True
            threading.Thread(target=self.run, name='runtime-emoji', daemon=True).start()
            log.info('Auto Telegram Emoji %s: worker started, %s templates', VERSION, sum((len(v) for v in self.cat.data.values())))

    def alert(self, oid, message):
        if oid in self.alerted:
            return
        self.alerted.add(oid)
        log.error('Emoji order %s: %s', oid, message)
        if not self.k.telegram:
            return
        from auto_telegram_emoji.platform import emoji, escape_html
        for user in self.k.telegram.authorized_users:
            try:
                self.k.telegram.bot.send_message(user, emoji('info') + ' <b>Auto Telegram Emoji</b>\nЗаказ <code>' + escape_html(oid) + '</code>\n' + escape_html(message) + '\nСостояние сохранено.', parse_mode='HTML')
            except Exception:
                log.warning('Emoji owner notification failed')

    def event_order(self, e):
        self.store.enqueue('order:' + str(e.order.id), 0, str(e.order.id))

    def event_message(self, e):
        m = e.message
        kind = getattr(getattr(m, 'type', None), 'name', '')
        if kind in {'NEW_FEEDBACK', 'FEEDBACK_CHANGED', 'ORDER_CONFIRMED', 'ORDER_CONFIRMED_BY_ADMIN'} and m.author_id <= 0:
            import re
            match = re.search('#([A-Z0-9]{8})(?![A-Z0-9])', m.text or '')
            if match and self.store.get(match[1]):
                self.store.enqueue('observe:' + str(m.id), 0, json.dumps({'observe': match[1]}))
                self.last_poll = 0
            return
        if m.author_id <= 0 or m.author_id == self.k.account.id or getattr(m, 'by_bot', False):
            return
        if getattr(getattr(m, 'type', None), 'name', 'NON_SYSTEM') != 'NON_SYSTEM':
            return
        if getattr(m, 'interlocutor_id', m.author_id) != m.author_id:
            return
        from .aliases import normalize
        command = normalize(m.text or '').split(' ', 1)[0]
        if len(m.text or '') > 2048 or not self.gate.accepts(m.author_id, m.id, command):
            return
        heavy = command in {'!пример', '!редактировать', '!градиент', '!шрифт', '!цвет', '!коллекции', '!сравнить', '!фон', '!стиль'}
        if not self.gate.rate(m.author_id, heavy):
            return
        from .aliases import normalize, ALIASES
        normal = normalize(m.text or '')
        orders = [o for o in self.store.all() if o['buyer'] == m.author_id and o['stage'] not in TERMINAL and (o['data'].get('kind') != 'public')]
        pub = self.store.get('PUBLIC-' + str(m.author_id))
        if not orders and normal.split(' ', 1)[0] not in ALIASES and (not (pub and pub['stage'] != 'public')):
            return
        self.store.enqueue('message:' + str(m.chat_id) + ':' + str(m.id), m.author_id, m.text or '')

    def event_status(self, e):
        if e.order.status.name in {'CLOSED', 'REFUNDED', 'PARTIALLY_REFUNDED', 'CANCELLED'}:
            o = self.store.get(e.order.id)
            if o:
                self.store.close(o['id'], 'REFUNDED' if 'REFUND' in e.order.status.name else 'CLOSED')
                self.store.enqueue('status:' + o['id'] + ':' + e.order.status.name, 0, json.dumps({'observe': o['id']}))
                self.last_poll = 0

    def accept(self, oid):
        cfg = self.config()
        if not cfg.get('enabled') or self.store.get(oid):
            return
        remote = self.k.account.get_order(oid)
        if remote.status.name != 'PAID' or remote.seller_id != self.k.account.id or getattr(remote.currency, 'name', '') != 'RUB':
            return
        from .bindings import match_order
        match = match_order(remote, cfg)
        if len(match) != 1:
            return
        lot_id, lot = match[0]
        units = remote.amount
        qty = units * int(lot.get('pack_size', 1))
        if isinstance(units, bool) or not isinstance(units, int) or (not 1 <= qty <= 200):
            self.alert(oid, 'Количество вне диапазона 1–200. Требуется ручная проверка.')
            return
        from .payments import sufficient, expected_total
        if not sufficient(remote.sum, lot['seller_price_rub'], units):
            self.alert(oid, 'Сумма заказа ниже установленной цены.')
            return
        self.store.add(remote.id, remote.buyer_id, remote.chat_id, qty)
        self.store.patch(remote.id, purchase_units=units, pack_size=int(lot.get('pack_size', 1)), lot_id=lot_id, summary=remote.short_description, expected_total_rub=str(expected_total(lot['seller_price_rub'], units)))
        log.info('Emoji accepted order %s qty=%s', oid, qty)

    def check_paid(self, o):
        if o['data'].get('wallet_job'):
            with self.store.tx() as db:
                r = db.execute('SELECT state FROM bonus_reservations WHERE oid=? AND buyer=?', (o['id'], o['buyer'])).fetchone()
            return bool(r and r['state'] in {'reserved', 'spent'})
        parent = o['data'].get('bonus_parent')
        r = self.k.account.get_order(parent or o['id'])
        if parent:
            valid = r.status.name in {'PAID', 'CLOSED'} and r.buyer_id == o['buyer'] and (r.seller_id == self.k.account.id) and (int(r.amount) == int(o['data']['origin_paid_qty'])) and (str(r.chat_id) == o['chat'])
            if not valid:
                self.store.close(o['id'], 'CANCELLED')
            return valid
        if r.status.name != 'PAID':
            if r.status.name in {'CLOSED', 'REFUNDED', 'PARTIALLY_REFUNDED', 'CANCELLED'}:
                self.store.close(o['id'], 'REFUNDED' if 'REFUND' in r.status.name else 'CLOSED')
            return False
        from .payments import cents
        return r.buyer_id == o['buyer'] and r.seller_id == self.k.account.id and (int(r.amount) == o['data'].get('purchase_units', o.get('paid_qty', o['qty']))) and (str(r.chat_id) == o['chat']) and (getattr(r.currency, 'name', '') == 'RUB') and (not o['data'].get('expected_total_rub') or cents(r.sum) >= cents(o['data']['expected_total_rub']))

    def sync_queue(self):
        rows = []
        for o in self.store.all():
            if o['data'].get('kind') in {'public', 'archive'}:
                continue
            item = dict(o)
            item['updated'] = o['created']
            done = o['stage'] in TERMINAL or o['stage'] == 'delivered'
            item['stage'] = 'COMPLETED' if done else o['stage']
            rows.append(item)
        self.queue.sync(SERVICE_ID, rows)

    def poll(self):
        cfg = self.config()
        stamp = json.dumps(cfg.get('lots', {}), sort_keys=True)
        if stamp != self.config_stamp:
            self.ignored_orders.clear()
            self.config_stamp = stamp
        if cfg.get('enabled'):
            _, sales, _, _ = self.k.account.get_sales(include_closed=False, include_refunded=False, include_paid=True)
            for s in sales:
                if not self.store.get(s.id) and s.id not in self.ignored_orders:
                    self.accept(s.id)
                    if not self.store.get(s.id):
                        self.ignored_orders.add(s.id)
        for o in self.store.all():
            if o['data'].get('kind') in {'public', 'archive'}:
                continue
            if o['data'].get('wallet_job'):
                continue
            if o['data'].get('bonus_parent'):
                if o['data'].get('bonus_expires', time.time() + 1) < time.time():
                    self.store.close(o['id'], 'CLOSED')
                elif o['stage'] not in TERMINAL:
                    self.check_paid(o)
            elif o['stage'] not in {'REFUNDED', 'CANCELLED'}:
                if o['stage'] == 'CLOSED' and time.time() - o['data'].get('aftercare_checked', 0) < 86400:
                    continue
                if o['buyer'] in self.futures and (not self.futures[o['buyer']].done()):
                    continue
                remote = self.k.account.get_order(o['id'])
                if remote.seller_id == self.k.account.id:
                    self.lifecycle.observe(o, remote)

    def tick(self):
        self.sync_queue()
        with self.store.tx() as db:
            events = [dict(row) for row in db.execute("SELECT * FROM inbox WHERE state='pending' AND buyer=0 ORDER BY created LIMIT 20")]
        for event in events:
            try:
                if event['text'].startswith('{'):
                    oid = json.loads(event['text'])['observe']
                    order = self.store.get(oid)
                    if order and order['buyer'] in self.futures and (not self.futures[order['buyer']].done()):
                        continue
                    if order:
                        remote = self.k.account.get_order(oid)
                        if remote.seller_id == self.k.account.id:
                            self.lifecycle.observe(order, remote)
                else:
                    self.accept(event['text'])
                with self.store.tx() as db:
                    db.execute("UPDATE inbox SET state='done' WHERE key=?", (event['key'],))
            except Exception:
                log.exception('Emoji event pending: %s', event['key'])
        self.sync_queue()
        buyers = {o['buyer'] for o in self.store.all() if o['stage'] not in TERMINAL | {'delivered'} and o['data'].get('kind') not in {'public', 'archive'} and (not o['data'].get('started') or o['stage'] in {'intro_pending', 'catalog_pending', 'generating', 'refund_requested'} or o['data'].get('bonus_notice_pending'))}
        with self.store.tx() as db:
            buyers.update((row[0] for row in db.execute("SELECT DISTINCT buyer FROM inbox WHERE state='pending' AND buyer>0")))
            buyers.update((row[0] for row in db.execute("SELECT DISTINCT o.buyer FROM orders o JOIN outbox b ON b.oid=o.id WHERE b.state IN ('pending','sending','uncertain') AND o.stage NOT IN ('REFUNDED','CANCELLED')")))
        for buyer in list(self.futures):
            future = self.futures[buyer]
            if future.done():
                try:
                    future.result()
                except Exception as error:
                    self.alert('buyer:' + str(buyer), type(error).__name__ + ': ' + str(error)[:120])
                del self.futures[buyer]
        for buyer in sorted(buyers):
            if self.stop.is_set():
                return
            if len(self.futures) >= 10:
                break
            if buyer not in self.futures:
                self.futures[buyer] = self.executor.submit(self.tick_buyer, buyer)

    def tick_buyer(self, buyer):
        with self.store.tx() as db:
            rows = [dict(r) for r in db.execute("SELECT * FROM inbox WHERE state='pending' AND buyer=? ORDER BY created LIMIT 20", (buyer,))]
        for r in rows:
            if not r['buyer']:
                if r['text'].startswith('{'):
                    oid = json.loads(r['text'])['observe']
                    o = self.store.get(oid)
                    if o:
                        remote = self.k.account.get_order(oid)
                        if remote.seller_id == self.k.account.id:
                            self.lifecycle.observe(o, remote)
                else:
                    self.accept(r['text'])
            else:
                from .aliases import normalize
                command = normalize(r['text']).split(' ', 1)[0]
                if r['key'].startswith('message:') and (not self.gate.accepts(r['buyer'], int(r['key'].split(':')[-1]), command)):
                    with self.store.tx() as db:
                        db.execute("UPDATE inbox SET state='ignored' WHERE key=?", (r['key'],))
                    continue
                current = self.queue.current(r['buyer'])
                o = self.store.get(current['order_id']) if current and current['plugin'] == SERVICE_ID else None
                chat = r['key'].split(':')[1] if r['key'].startswith('message:') else o['chat'] if o else ''
                try:
                    handled = self.public.handle(r['buyer'], chat, r['text'], r['key'], o)
                except ValueError as error:
                    pub = self.store.get('PUBLIC-' + str(r['buyer']))
                    if pub:
                        self.store.event(pub, 'error:' + r['key'], str(error))
                        self.transport.flush(pub)
                    handled = True
                if handled:
                    with self.store.tx() as db:
                        db.execute("UPDATE inbox SET state='done' WHERE key=?", (r['key'],))
                    continue
                if not o or o['stage'] in TERMINAL:
                    with self.store.tx() as db:
                        db.execute("UPDATE inbox SET state='done' WHERE key=?", (r['key'],))
                    continue
                if o['stage'] != 'delivered' and (not self.queue.claim(SERVICE_ID, o)):
                    continue
                if not o['data'].get('started'):
                    continue
                self.transport.flush(o)
                if r['key'].startswith('message:') and (not self.gate.accepts(r['buyer'], int(r['key'].split(':')[-1]), command)):
                    with self.store.tx() as db:
                        db.execute("UPDATE inbox SET state='ignored' WHERE key=?", (r['key'],))
                    continue
                if not self.check_paid(o):
                    continue
                try:
                    self.engine.handle(o, r['text'], r['key'])
                except (RuntimeError, TimeoutError) as error:
                    self.store.event(o, 'render-error:' + r['key'], 'Предпросмотр пока не готов. Данные сохранены. Можно изменить текст или написать продавцу: !продавец.')
                    self.alert(o['id'], 'Ошибка рендера: ' + type(error).__name__)
                    with self.store.tx() as db:
                        db.execute("UPDATE inbox SET state='failed' WHERE key=?", (r['key'],))
                    continue
                changed = self.store.get(o['id'])
                if changed['data'].get('owner_help_requested'):
                    self.alert(o['id'], 'Покупатель просит помощи.')
                    self.store.patch(o['id'], owner_help_requested=False)
            with self.store.tx() as db:
                db.execute("UPDATE inbox SET state='done' WHERE key=?", (r['key'],))
        for o in self.store.all():
            if o['buyer'] != buyer:
                continue
            if o['data'].get('kind') in {'public', 'archive'}:
                self.transport.flush(o)
                continue
            if o['stage'] in TERMINAL:
                self.transport.flush(o, events_only=True)
                continue
            if o['stage'] == 'delivered':
                self.engine.wallet.settle(o['id'], True)
                self.transport.flush(o)
                continue
            if not self.queue.claim(SERVICE_ID, o):
                position = max(1, self.queue.position(o['id']))
                if o['data'].get('queue_position') != position:
                    self.store.patch(o['id'], queue_position=position)
                    self.store.event(o, 'queue:' + str(position), f'Заказ принят. Вы в очереди: №{position}.\nНачну автоматически, когда освободится место. !статус — проверить заказ.')
                    self.transport.flush(o)
                continue
            if o['data'].get('bonus_notice_pending') and (not o['data'].get('bonus_parent')):
                self.lifecycle.notice(o)
                o = self.store.get(o['id'])
            if not o['data'].get('started'):
                if not self.check_paid(o):
                    continue
                from auto_telegram_emoji.platform import selected
                selected(self.root, o['buyer'], SERVICE_ID)
                self.engine.start(o)
                o['data']['started'] = True
                self.store.save(o)
            if not self.allowed():
                return
            if o['stage'] == 'refund_requested':
                self.refund(o)
                continue
            if o['stage'] == 'intro_pending':
                if time.time() < o['data'].get('intro_retry_at', 0):
                    continue
                if not self.check_paid(o):
                    continue
                self.transport.flush(o)
                self.gate.begin(o)
                try:
                    self.engine.collections(o)
                    self.store.save(o)
                except (RuntimeError, TimeoutError):
                    self.store.patch(o['id'], intro_retry_at=time.time() + 30)
                    self.alert(o['id'], 'Первый каталог ожидает повторной подготовки.')
                    continue
            if o['stage'] == 'catalog_pending':
                if time.time() < o['data'].get('catalog_retry_at', 0):
                    continue
                if not self.check_paid(o):
                    continue
                self.transport.flush(o)
                self.gate.begin(o)
                try:
                    self.engine.send_catalog(o)
                except (RuntimeError, TimeoutError):
                    self.store.patch(o['id'], catalog_retry_at=time.time() + 30)
                    self.alert(o['id'], 'Отправка каталога ожидает повторной подготовки.')
                    continue
            if o['stage'] == 'generating':
                if time.time() < o['data'].get('pack_retry_at', 0):
                    continue
                if not self.check_paid(o):
                    continue
                self.transport.flush(o)
                try:
                    self.engine.finish(o)
                except (RuntimeError, TimeoutError) as error:
                    from .packs import PackPending
                    if isinstance(error, PackPending):
                        self.store.patch(o['id'], pack_retry_at=time.time() + error.delay)
                        continue
                    current = self.store.get(o['id'])
                    current['stage'] = 'REVIEW'
                    self.store.save(current)
                    self.store.event(current, 'render-review', 'Сборка требует проверки продавцом. Ваши настройки сохранены; повторно оплачивать заказ не нужно.')
                    self.alert(o['id'], 'Сборка требует проверки: ' + type(error).__name__)
            self.transport.flush(self.store.get(o['id']))

    def refund(self, o):
        if o['data'].get('templates_confirmed'):
            self.alert(o['id'], 'Отмена после фиксации выбора отклонена.')
            return
        if o['data'].get('wallet_job'):
            self.engine.wallet.settle(o['id'], False)
            self.store.event(o, 'cancelled', 'Набор отменён. Бонусы возвращены на баланс.')
            self.store.close(o['id'], 'CLOSED')
            return
        remote = self.k.account.get_order(o['id'])
        if remote.status.name == 'REFUNDED':
            self.engine.wallet.settle(o['id'], False)
            self.store.event(o, 'refunded', 'Возврат подтверждён FunPay.')
            self.store.close(o['id'], 'CLOSED')
            return
        if remote.status.name != 'PAID' or not self.check_paid(o):
            return
        if o['data'].get('refund_state') in {'sending', 'uncertain'}:
            self.alert(o['id'], 'Результат возврата неизвестен. Требуется сверка; повтор не выполняется.')
            return
        self.store.patch(o['id'], refund_state='sending')
        try:
            self.k.account.refund(o['id'])
        except Exception:
            self.store.patch(o['id'], refund_state='uncertain')
            return
        verified = self.k.account.get_order(o['id'])
        if verified.status.name == 'REFUNDED':
            self.engine.wallet.settle(o['id'], False)
            self.store.event(o, 'refunded', 'Возврат подтверждён FunPay.')
            self.store.close(o['id'], 'CLOSED')
        else:
            self.store.patch(o['id'], refund_state='uncertain')

    def run(self):
        while not self.stop.is_set():
            try:
                if self.allowed():
                    if time.time() - self.last_poll > 30:
                        self.poll()
                        self.last_poll = time.time()
                    self.tick()
                    from .support import Support
                    Support(self).deliver()
                    if time.time() - self.last_cleanup > 3600:
                        from .artifacts import Artifacts
                        Artifacts(self.store).collect()
                        self.last_cleanup = time.time()
            except Exception as e:
                log.exception('Emoji worker failed')
                self.alert('worker', type(e).__name__ + ': ' + str(e)[:180])
            self.stop.wait(3)
