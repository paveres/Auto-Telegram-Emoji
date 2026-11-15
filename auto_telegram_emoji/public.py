__author__ = '@justmeth'
__channel__ = 'https://t.me/g_plugins'
__contact__ = 'https://t.me/justmeth'
from .links import base_url
'Buyer commands outside an active editing step; all replies use the durable outbox.'
import hashlib, secrets, time
from pathlib import Path
from .aliases import normalize, ALIASES
from .catalog import NAMES

class Public:

    def __init__(self, adapter):
        self.a = adapter

    def handle(self, buyer, chat, text, key, active=None):
        a = self.a
        s = a.store
        pid = 'PUBLIC-' + str(buyer)
        p = s.get(pid)
        if not p:
            s.add(pid, buyer, chat, 0)
            p = s.get(pid)
            p['stage'] = 'public'
            p['data'].update(kind='public', started=True)
            s.save(p)
        raw = text
        text = normalize(text, p['stage'])
        parts = text.split(maxsplit=1)
        cmd = parts[0] if parts else ''
        arg = parts[1] if len(parts) > 1 else ''
        if cmd == '!саппорт' or p['stage'].startswith('support_'):
            if cmd not in {'!меню', '!статус', '!мои', '!продавец'}:
                from .support import Support
                return Support(a).handle(p, raw, key, active)
        if active and active['stage'] not in {'delivered', 'CLOSED', 'REFUNDED', 'CANCELLED'} and (cmd not in {'!меню', '!продавец', '!мои'}) and (not (cmd == '!статус' and (not active['data'].get('started')))) and (p['stage'] not in {'archive_pick', 'archive_confirm'}):
            return False
        supported = {'!меню', '!коллекции', '!пример', '!бонус', '!статус', '!файлы', '!пак', '!продавец', '!шрифт', '!градиент', '!цвет', '!редактировать', '!стиль', '!мои'}
        if cmd in {'!отмена', '!назад', '!продолжить'} and p['stage'] != 'public':
            p['stage'] = 'public'
            s.save(p)
            s.emit(p, 'exit:' + key, 'Вернулись к заказу. !продолжить — текущий шаг; !меню — команды.')
            a.transport.flush(p)
            return True
        if cmd not in supported and p['stage'] not in {'wallet_confirm', 'archive_pick', 'archive_confirm'}:
            return False
        p['data']['rev'] = key

        def say(label, value):
            s.emit(p, label, value)
        if p['data'].get('last_input') == key:
            return True
        from .archive import Archive
        archive = Archive(s)
        if cmd == '!мои':
            from datetime import datetime
            creations = archive.creations(buyer)
            p['data']['archive_choices'] = [o['id'] for o in creations]
            p['stage'] = 'archive_pick' if creations else 'public'
            say('my-creations', '💙【 Ваши созданные эмодзи 】\n\n' + '\n'.join((f"{i}. {datetime.fromtimestamp(o['created']).strftime('%d.%m.%Y')} · {o['qty']} эмодзи · {o['data'].get('nick', 'без текста')[:16]}" for i, o in enumerate(creations, 1))) + ('\n\nВведите номер набора.' if creations else 'Готовых наборов пока нет.'))
        elif cmd == '!меню':
            say('help', a.engine.help())
        elif cmd == '!продавец':
            a.alert(active['id'] if active else pid, 'Покупатель просит помощи в чате ' + str(chat))
            say('seller', 'Продавец уведомлён. Напишите вопрос здесь.')
        elif p['stage'] in {'archive_pick', 'archive_confirm'}:
            if text in {'!отмена', '!назад', '-'}:
                p['stage'] = 'public'
                say('archive-cancel', 'Выдача отменена. Файлы сохранены. !мои — список.')
            elif p['stage'] == 'archive_pick':
                choices = p['data']['archive_choices']
                if not text.isdigit() or not 1 <= int(text) <= len(choices):
                    say('archive-number', 'Введите номер набора из списка. !отмена — выйти.')
                else:
                    oid = choices[int(text) - 1]
                    creation = next((x for x in archive.creations(buyer) if x['id'] == oid), None)
                    if not creation:
                        raise ValueError('Файлы сейчас недоступны. !продавец — помощь.')
                    p['data']['archive_selected'] = oid
                    p['stage'] = 'archive_confirm'
                    from .input_gate import InputGate
                    InputGate(s).begin(p)
                    for i, path in enumerate(sorted(Path(creation['archive']).parent.glob('preview-*.jpg'))):
                        s.emit(p, 'creation-photo' + str(i), path, 'image')
                    from datetime import datetime
                    reason = 'За накопленные бонусы: ' + str(creation['qty']) if creation['data'].get('wallet_job') else 'За отзыв о заказе ' + creation['data']['bonus_parent'] if creation['data'].get('bonus_parent') else 'Покупка на FunPay, пакет ' + str(creation['data'].get('pack_size', 1))
                    say('creation-info', f"💙【 Информация о наборе 】\nСоздан: {datetime.fromtimestamp(creation['created']).strftime('%d.%m.%Y')}\nОснование: {reason}\nЗаказ: {oid}\nЭмодзи: {creation['qty']}\nТекст: {creation['data'].get('nick', '')}" + (' / ' + creation['data']['text2'] if creation['data'].get('text2') else '') + ('\n\nПолучить ссылку на пак? Да / нет' if creation['data'].get('pack_urls') else '\n\nПолучить ZIP этого набора? Да / нет'))
            elif text == '+':
                creation = next((x for x in archive.creations(buyer) if x['id'] == p['data']['archive_selected']), None)
                if not creation:
                    raise ValueError('Набор не найден. !мои — список.')
                if creation['data'].get('pack_urls'):
                    from .packs import links
                    say('archive-link', links(creation) + '\n\n!пак — повторить ссылку.')
                else:
                    url = archive.renew(creation, buyer, key)
                    say('archive-link', 'Ваши эмодзи готовы к скачиванию:\n' + url + '\n\nЕсли понадобится новая ссылка — !мои.')
                p['stage'] = 'public'
            else:
                say('archive-answer', 'Подтвердите получение выбранного набора: да / нет.')
        elif p['stage'] == 'wallet_confirm':
            if text == '+':
                count = p['data']['wallet_count']
                oid = p['data']['wallet_job_id']
                a.engine.wallet.reserve(buyer, oid, count)
                s.add(oid, buyer, chat, count)
                job = s.get(oid)
                job['data'].update(wallet_job=True, review_seen=True)
                s.save(job)
                say('gift-start', 'Бонусы зарезервированы. Начинаем выбор бесплатного набора.')
                p['stage'] = 'public'
            elif text in {'-', '!отмена', '!назад'}:
                p['stage'] = 'public'
                say('gift-cancel', 'Бонусы не использованы.')
            else:
                say('gift-confirm', 'Подтвердите использование бонусов: да / нет.')
        elif cmd == '!меню':
            say('help', a.engine.help())
        elif cmd == '!бонус':
            balance = a.engine.wallet.balance(buyer)
            if arg.lower().startswith(('использовать ', 'use ', 'потратить ')):
                try:
                    count = int(arg.split()[-1])
                except ValueError:
                    count = 0
                if not 1 <= count <= min(200, balance):
                    say('balance-error', 'Укажите от 1 до ' + str(min(200, balance)) + ' доступных бонусов.')
                else:
                    p['stage'] = 'wallet_confirm'
                    p['data'].update(wallet_count=count, wallet_job_id='GIFT' + hashlib.sha256(key.encode()).hexdigest()[:12].upper())
                    say('gift-confirm', f'Использовать {count} бонусов отдельным бесплатным набором?\nПодтвердите: да / нет.')
            else:
                history = a.engine.wallet.history(buyer)
                say('balance', '💙【 Бонусный баланс 】\nДоступно: ' + str(balance) + '\nБонусы не сгорают.\n!бонус использовать 2 — собрать 2 бесплатных эмодзи.\n\nПоследние операции:\n' + '\n'.join((f"{r['delta']:+d} — {r['reason']}" for r in history)))
        elif cmd in {'!коллекции', '!пример'}:
            if arg.isdigit() and 1 <= int(arg) <= len(a.cat.collections()):
                c = a.cat.collections()[int(arg) - 1]
                paths = a.render.collection(c)
                say('catalog-title', NAMES[c] + ': ' + str(len(a.cat.items(c))) + ' вариантов. Выбор доступен после оплаты или использования бонусов.')
            else:
                paths = a.render.collections()
                say('catalog', '\n'.join((f'{i}. {NAMES[c]}' for i, c in enumerate(a.cat.collections(), 1))) + '\n!коллекции 2 — посмотреть коллекцию №2. Для своего набора купите лот или используйте бонусы.')
            from .input_gate import InputGate
            InputGate(s).begin(p)
            for i, path in enumerate(paths):
                s.emit(p, 'catalog-img' + str(i), path, 'image')
        elif cmd == '!пак':
            from .packs import links
            orders = [o for o in s.all() if o['buyer'] == buyer and o['stage'] in {'delivered', 'CLOSED'} and o['data'].get('pack_urls')]
            say('packs', '\n\n'.join(('Заказ ' + o['id'] + '\n' + links(o) for o in orders[-5:])) if orders else 'Для повторного получения старого набора: !мои.')
        elif cmd == '!файлы':
            orders = [o for o in s.all() if o['buyer'] == buyer and o['stage'] == 'delivered' and o['data'].get('token')]
            if orders:
                say('files', '\n'.join(('Заказ ' + o['id'] + ': ' + base_url() + '/' + o['data']['token'] + '/download' for o in orders[-5:])))
            else:
                say('no-files', 'Для повторного получения старого набора: !мои.\nДля помощи: !продавец.')
        elif cmd == '!статус':
            from .texts import stage_name
            say('status', '\n'.join((o['id'] + ' — ' + ('В очереди: №' + str(max(1, a.queue.position(o['id']))) if o['stage'] not in {'delivered', 'CLOSED', 'REFUNDED', 'CANCELLED'} and (not o['data'].get('started')) else stage_name(o['stage'])) for o in s.all() if o['buyer'] == buyer and o['data'].get('kind') not in {'public', 'archive'})) or 'Заказов эмодзи пока нет. Получить команды')
        elif cmd == '!продавец':
            a.alert(active['id'] if active else pid, 'Покупатель просит помощи в чате ' + str(chat))
            say('seller', 'Продавец уведомлён. Напишите свой вопрос здесь.')
        elif cmd in {'!шрифт', '!градиент'}:
            from .editor import FONTS
            from .gradients import THEMES
            from .vector import transform
            names = FONTS if cmd == '!шрифт' else [t[0] for t in THEMES]
            raws = []
            for i in range(len(names)):
                raws.append(transform(a.cat.get('classic', 1), 'DEMO', a.cat.base / 'fonts', style={'font': FONTS[i]} if cmd == '!шрифт' else {'theme': i + 1, 'text_color': '#FFFFFF'}))
            from .input_gate import InputGate
            InputGate(s).begin(p)
            for i, path in enumerate(a.render.cards(raws, a.render.folder / 'cache' / ('public-' + cmd[1:]))):
                s.emit(p, 'samples' + str(i), path, 'image')
            say('samples-label', '\n'.join((f'{i}. {name}' for i, name in enumerate(names, 1))) + '\nНастроить свой набор можно после выбора оплаченных или бонусных эмодзи.')
        else:
            say('available', 'Эта настройка доступна в редакторе своего набора. Купите лот или используйте накопленные бонусы.\nПолучить команды')
        p['data']['last_input'] = key
        s.save(p)
        a.transport.flush(p)
        return True
