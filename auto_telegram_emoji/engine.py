__author__ = '@justmeth'
__channel__ = 'https://t.me/g_plugins'
__contact__ = 'https://t.me/justmeth'
import copy, hashlib, secrets, time
from .parser import numbers
from .catalog import NAMES
from . import texts
from .links import base_url
from .textflow import handle as handle_text, open_menu as text_menu

class Engine:

    def __init__(self, store, cat, renderer):
        self.store = store
        self.cat = cat
        self.render = renderer
        from .wallet import Wallet
        self.wallet = Wallet(store)

    def emit(self, o, key, text, kind='text'):
        self.store.emit(o, key, text, kind)

    def photos(self, o, key, paths):
        if paths:
            from .input_gate import InputGate
            InputGate(self.store).begin(o)
        for i, p in enumerate(paths):
            self.emit(o, key + str(i), p, 'image')

    def collections(self, o):
        o['stage'] = 'collection'
        self.photos(o, 'collections', self.render.collections())
        self.emit(o, 'prompt', texts.collections(self.cat, o))

    def cart(self, o):
        self.emit(o, 'cart', texts.cart(self.cat, o))
        if o['data']['cart']:
            _, pages, _ = self.render.selected(o)
            self.photos(o, 'cart-img', pages)
        if len(o['data']['cart']) == o['qty']:
            o['stage'] = 'confirm'
            self.emit(o, 'confirm', 'Подтвердить варианты: + / −\nПосле + заменить варианты нельзя.\n!смена — выбрать заново')
        else:
            o['stage'] = 'selection_action'
            self.emit(o, 'more', f"Выбрано: {len(o['data']['cart'])}/{o['qty']}\nОсталось выбрать: {o['qty'] - len(o['data']['cart'])}\n\n1. Выбрать из другой коллекции\n2. Добавить из этой коллекции\n\nОтветьте цифрой.\n!убрать 2 — убрать эмодзи №2 из набора")

    def link(self, o, video, archive=None):
        d = o['data']
        token = d.get('token')
        if not token:
            while True:
                token = ''.join((secrets.choice('abcdefghijklmnopqrstuvwxyz0123456789') for _ in range(8)))
                with self.store.tx() as db:
                    exists = db.execute('SELECT 1 FROM links WHERE token=?', (hashlib.sha256(token.encode()).hexdigest(),)).fetchone()
                if not exists:
                    break
            d['token'] = token
        with self.store.tx() as db:
            db.execute('INSERT INTO links VALUES(?,?,1,?,?) ON CONFLICT(token) DO UPDATE SET video=excluded.video,archive=excluded.archive,active=1', (hashlib.sha256(token.encode()).hexdigest(), o['id'], str(video), str(archive) if archive else None))
        return base_url() + '/' + token

    def preview(self, o):
        pages, video, _ = self.render.build(o)
        url = self.link(o, video)
        self.photos(o, 'personal', pages)
        self.emit(o, 'preview', texts.preview(o) + '\n\nАнимация: ' + url)
        o['stage'] = 'preview'

    def prepare_catalog(self, o, c):
        o['data']['collection'] = c
        o['stage'] = 'catalog_pending'
        from .input_gate import InputGate
        InputGate(self.store).begin(o)
        self.emit(o, 'catalog-wait', 'Отправляю варианты. Дождитесь всех фотографий.')

    def send_catalog(self, o):
        d = o['data']
        c = d['collection']
        self.photos(o, 'catalog', self.render.collection(c))
        o['stage'] = 'select'
        self.emit(o, 'select', f"💙【 {NAMES[c]} 】\n\nВ коллекции: {len(self.cat.items(c))}\nВыбрано: {len(d['cart'])}/{o['qty']}\n\nВыберите понравившиеся эмодзи: 1–{len(self.cat.items(c))}.\nНапример: 1, 5, 47\n!коллекции — другая коллекция")
        self.store.save(o)

    def start(self, o):
        if o['data'].get('bonus_parent'):
            self.store.event(o, 'review-bonus', '💙【 Спасибо за отзыв! 】\n\nНачислено: +2 эмодзи бесплатно.\nОсновной набор сохранён. Выберите 2 бонусных варианта.\nНик и оформление основного набора сохранены.')
            o['data']['bonus_notice_pending'] = False
        else:
            self.emit(o, 'paid', f"💙【 Эмодзи с вашим ником 】\n\nЗаказ: #{o['id']}\nОплачено: {o.get('paid_qty', o['qty'])} эмодзи\n1 единица заказа = 1 эмодзи.")
        self.emit(o, 'start-reminder', 'Напоминание:\n\nНЕ СПАМЬТЕ БОТУ. ОН ВИДИТ ВАШИ СООБЩЕНИЯ. ОТПРАВЛЯЙТЕ ЦИФРЫ, ТЕКСТ И ДРУГИЕ ДАННЫЕ ОДИН РАЗ И ЖДИТЕ ОТВЕТА.')
        o['stage'] = 'intro_pending'
        from .input_gate import InputGate
        InputGate(self.store).begin(o)
        self.store.save(o)

    def handle(self, o, text, msgid):
        if o['data'].get('last_input') == str(msgid):
            return
        from .aliases import normalize
        text = normalize(text, o['stage'])
        from .admission import accepts
        if not accepts(o, text, self.cat):
            return
        if o['stage'] == 'select' and text.startswith('!добавить '):
            text = text.split(maxsplit=1)[1]
        original = copy.deepcopy(o)
        d = o['data']
        d['rev'] += 1
        text = text.strip()
        cmd = text.lower()
        stage = o['stage']
        try:
            from .editor import handle as edit
            if cmd == '!меню':
                self.emit(o, 'menu', self.help())
            elif cmd.startswith('!бонус'):
                parts = text.split()
                if len(parts) == 3 and parts[1].lower() in {'использовать', 'потратить', 'use'}:
                    try:
                        amount = int(parts[2])
                    except ValueError:
                        raise ValueError('Укажите количество бонусов целым числом.')
                    if stage in {'delivered', 'generating'}:
                        raise ValueError('Этот набор уже собран. Используйте бонусы отдельным набором через меню после завершения заказа.')
                    if not 1 <= amount <= 200 or o.get('paid_qty', o['qty']) + int(d.get('bonus_qty', 0)) + amount > 200:
                        raise ValueError('В наборе может быть максимум 200 эмодзи.')
                    if self.wallet.balance(o['buyer']) < amount:
                        raise ValueError('На балансе недостаточно бонусов.')
                    d['wallet_previous_stage'] = stage
                    d['pending_wallet_amount'] = amount
                    o['stage'] = 'wallet_use_confirm'
                    self.emit(o, 'wallet-confirm', f'Использовать {amount} бонусов в этом наборе?\nПодтвердите: + / −')
                else:
                    self.emit(o, 'wallet', '💙【 Бонусный баланс 】\nДоступно: ' + str(self.wallet.balance(o['buyer'])) + '\n!бонус использовать 2 — добавить 2 бонуса к текущему набору.\nБонусы можно копить и использовать позже.')
            elif stage == 'wallet_use_confirm':
                if text == '+':
                    self.wallet.reserve(o['buyer'], o['id'], d['pending_wallet_amount'])
                    d['wallet_bonus_qty'] = d.pop('pending_wallet_amount')
                    o['qty'] = o.get('paid_qty', o['qty']) + int(d.get('bonus_qty', 0)) + d['wallet_bonus_qty']
                    if d.get('templates_confirmed'):
                        d['locked_cart'] = copy.deepcopy(d['cart'])
                    self.collections(o)
                    self.emit(o, 'wallet-added', 'Бонусы зарезервированы. Доберите варианты. Списание произойдёт при выдаче готовых файлов.')
                elif text in {'-', '!назад', '!отмена'}:
                    o['stage'] = d.pop('wallet_previous_stage')
                    self.emit(o, 'wallet-no', 'Бонусы не использованы. Продолжаем прежний шаг.')
                else:
                    raise ValueError('Подтвердите использование бонусов: + / −')
            elif cmd == '!продолжить':
                if stage == 'nick':
                    self.emit(o, 'resume-nick', 'Введите никнейм для эмодзи. До 16 символов.')
                elif stage in {'text_pick', 'text_value'}:
                    text_menu(self, o)
                elif stage == 'selection_action':
                    self.cart(o)
                elif stage == 'pack_type':
                    self.emit(o, 'pack-type', 'Что создаём?\n\n1. Стикер-пак\n2. Эмодзи-пак\n\nОтветьте цифрой.')
                elif d.get('nick') and stage not in {'generating', 'delivered', 'REVIEW', 'refund_requested', 'refund_confirm', 'wallet_use_confirm'}:
                    self.preview(o)
                elif stage in {'collection', 'select', 'selection_action', 'confirm'}:
                    self.cart(o) if d.get('cart') else self.collections(o)
                else:
                    self.emit(o, 'resume', f'Текущий этап: {texts.STAGES.get(stage, stage)}.\n' + ('Введите никнейм.' if stage == 'nick' else '!статус — состояние; !продавец — помощь.'))
            elif handle_text(self, o, text):
                pass
            elif stage == 'selection_action' and text in {'1', '2'}:
                if text == '1':
                    self.collections(o)
                else:
                    c = d.get('collection')
                    if not c:
                        self.collections(o)
                    else:
                        self.prepare_catalog(o, c)
            elif stage == 'pack_type':
                if cmd in {'!назад', '!отмена'} or text in {'-', '−'}:
                    self.preview(o)
                elif text in {'1', '2'}:
                    d['pack_kind'] = 'regular' if text == '1' else 'custom_emoji'
                    o['stage'] = 'generating'
                    self.emit(o, 'building', 'Создаю пак. Настройки сохранены, повторять ответ не нужно.')
                else:
                    raise ValueError('Что создаём?\n\n1. Стикер-пак\n2. Эмодзи-пак\n\nОтветьте цифрой.')
            elif cmd in {'!назад', '!отмена'} and stage == 'preview':
                self.emit(o, 'back-editor', 'Вы вернулись к результату. !редактор — настройки; !предпросмотр — фото.\n+ — создать пак; − — продолжить редактирование.')
            elif cmd == '!бэк':
                if stage not in {'collection', 'select', 'selection_action', 'confirm'} or d.get('templates_confirmed'):
                    raise ValueError('Выбор уже подтверждён. Автоматическая отмена недоступна; !продавец — проверка вопроса.')
                d['refund_previous_stage'] = stage
                o['stage'] = 'refund_confirm'
                self.emit(o, 'refund-confirm', 'Отменить набор' + (' и вернуть оплату через FunPay' if not d.get('wallet_job') else ' и вернуть бонусы на баланс') + '?\nПодтвердите: + / −')
            elif stage == 'refund_confirm':
                if text == '+':
                    o['stage'] = 'refund_requested'
                    self.emit(o, 'refund-wait', 'Запрос отмены принят. Проверяю состояние заказа.')
                elif text in {'-', '!назад', '!отмена'}:
                    o['stage'] = d.pop('refund_previous_stage')
                    self.emit(o, 'refund-no', 'Отмена не выполнялась. Продолжаем выбор.')
                else:
                    raise ValueError('Подтвердите отмену: + / −')
            elif cmd == '!продавец':
                d['owner_help_requested'] = True
                self.emit(o, 'owner-help', 'Вопрос передан продавцу. Опишите его в этом чате; текущий этап сохранён.')
            elif cmd in {'!отмена', '!назад'} and (stage.startswith('editor_') or stage == 'edit_menu'):
                self.preview(o)
            elif cmd == '!отмена' and stage == 'preview' and d.get('undo'):
                from .editor import restore
                restore(d, d['undo'].pop())
                self.preview(o)
            elif edit(self, o, text):
                pass
            elif cmd in {'!статус', '!помощь', '!продолжить'}:
                self.emit(o, 'status', f"Заказ #{o['id']}\nЭтап: {texts.STAGES.get(stage, stage)}\nВыбрано: {len(d['cart'])}/{o['qty']}\n!корзина — выбор\n!коллекции — коллекции до подтверждения\n!текст, !цвет, !градиент — после подтверждения\n!файлы — готовый архив")
            elif stage == 'delivered' and d.get('pack_urls'):
                from .packs import links
                self.emit(o, 'pack', links(o) + '\n\n!пак — повторить ссылку.')
            elif stage == 'delivered':
                if cmd == '!файлы':
                    self.emit(o, 'files', 'Ваш архив: ' + base_url() + '/' + d['token'] + '/download')
                else:
                    self.emit(o, 'done', 'Файлы готовы. !файлы — получить ссылку повторно. Изменение заказа завершено.')
            elif cmd in {'!коллекции', '!назад', 'назад'} and stage in {'collection', 'select', 'selection_action', 'confirm'}:
                self.collections(o)
            elif cmd in {'!корзина', '!готово'} and stage in {'collection', 'select', 'selection_action', 'confirm'}:
                self.cart(o)
            elif cmd == '!смена' and stage in {'collection', 'select', 'selection_action', 'confirm'}:
                d['previous_cart'] = copy.deepcopy(d['cart'])
                d['cart'] = copy.deepcopy(d.get('locked_cart', []))
                self.collections(o)
                self.emit(o, 'change', 'Выбирайте новые варианты. Подтверждённые ранее сохранены. !отмена — вернуть предыдущий выбор.')
            elif cmd.startswith('!убрать ') and stage in {'collection', 'select', 'selection_action', 'confirm'}:
                ns = numbers(text.split(maxsplit=1)[1], len(d['cart']))
                if any((n <= len(d.get('locked_cart', [])) for n in ns)):
                    raise ValueError('Эти варианты уже подтверждены. Можно изменить только добавляемые бонусные варианты.')
                d['cart'] = [x for i, x in enumerate(d['cart'], 1) if i not in ns]
                o['stage'] = 'select' if d.get('collection') else 'collection'
                self.cart(o)
            elif cmd in {'!отмена', '!назад', 'назад'} and stage in {'nick_edit', 'color', 'gradient', 'style_confirm'}:
                for k, v in d.pop('backup', {}).items():
                    d[k] = v
                self.preview(o)
            elif cmd == '!отмена' and 'previous_cart' in d and (stage in {'collection', 'select', 'selection_action', 'confirm'}):
                d['cart'] = d.pop('previous_cart')
                self.cart(o)
            elif cmd in {'!текст', '!цвет', '!градиент'} and stage == 'preview':
                d['backup'] = {k: d[k] for k in ('nick', 'gradient', 'color')}
                if cmd == '!текст':
                    o['stage'] = 'nick_edit'
                    self.emit(o, 'nick-edit', 'Введите новый ник.\n!отмена — оставить прежний.')
                else:
                    o['stage'] = 'color' if cmd == '!цвет' else 'gradient'
                    names = texts.COLOR_NAMES if cmd == '!цвет' else texts.GRADIENT_NAMES
                    from .vector import transform
                    c, n = d['cart'][0]
                    raws = []
                    for i in range(len(names)):
                        raws.append(transform(self.cat.get(c, n), d['nick'], self.cat.base / 'fonts', (0 if i == 8 else i + 1) if cmd == '!градиент' else d['gradient'], i if cmd == '!цвет' else d['color']))
                    pages = self.render.cards(raws, self.render.folder / 'orders' / o['id'] / f"options-{d['rev']}")
                    self.photos(o, 'options', pages)
                    self.emit(o, 'options-text', '\n'.join((f'{i}. {name}' for i, name in enumerate(names, 1))) + '\n\nВыберите номер. !отмена — оставить прежнее.')
            elif cmd == 'назад' and stage in {'nick', 'nick_edit'}:
                self.emit(o, 'nick-back', 'Варианты уже подтверждены. Сейчас введите никнейм.\n!статус — состояние заказа.')
            elif cmd.startswith(('!', '/')) and (not (stage in {'nick', 'nick_edit'} and cmd.startswith('!текст '))):
                self.emit(o, 'bad-command', f'Команда недоступна на этапе «{texts.STAGES.get(stage, stage)}».\n!статус — что делать дальше. Ваши данные сохранены.')
            elif stage == 'collection':
                n = numbers(text, len(self.cat.collections()))
                if len(n) != 1:
                    raise ValueError('Выберите одну коллекцию.')
                c = self.cat.collections()[n[0] - 1]
                self.prepare_catalog(o, c)
            elif stage == 'select':
                if cmd.startswith('!добавить '):
                    text = text.split(maxsplit=1)[1]
                c = d['collection']
                ns = numbers(text, len(self.cat.items(c)))
                new = [[c, n] for n in ns if [c, n] not in d['cart']]
                if len(d['cart']) + len(new) > o['qty']:
                    raise ValueError(f"Превышен лимит выбора.\n\nДоступно: {o['qty']} эмодзи\nБонусных: {o['qty'] - o.get('paid_qty', o['qty'])}")
                d['cart'].extend(new)
                self.cart(o)
            elif stage == 'confirm':
                if text == '+':
                    if len(d['cart']) != o['qty']:
                        raise ValueError('Сначала выберите оплаченное количество.')
                    d.pop('previous_cart', None)
                    d['templates_confirmed'] = True
                    text_menu(self, o)
                elif text in {'-', '−'}:
                    o['stage'] = 'select' if d.get('collection') else 'collection'
                    self.emit(o, 'edit', 'Выбор сохранён.\n!убрать НОМЕР — убрать позицию корзины\n!коллекции — добавить варианты\n!смена — выбрать заново\n!готово — подтвердить')
                else:
                    raise ValueError('Подтвердите варианты: + / −. Либо !смена.')
            elif stage in {'nick', 'nick_edit'}:
                if text in {'+', '-', '−'}:
                    raise ValueError('Сейчас нужен никнейм. Введите текст для эмодзи.')
                d['nick'] = text.split(maxsplit=1)[1] if cmd.startswith('!текст ') else text
                self.preview(o)
                d.pop('backup', None)
            elif stage in {'color', 'gradient'}:
                ns = numbers(text, 9)
                if len(ns) != 1:
                    raise ValueError('Выберите один номер.')
                value = ns[0]
                d[stage] = value - 1 if stage == 'color' else 0 if value == 9 else value
                pages, video, _ = self.render.build(o)
                self.link(o, video)
                self.photos(o, 'style', pages)
                o['stage'] = 'style_confirm'
                self.emit(o, 'style-confirm', 'Применить это оформление ко всему набору: + / −')
            elif stage == 'style_confirm':
                if text == '+':
                    d.pop('backup', None)
                    self.preview(o)
                elif text in {'-', '−'}:
                    d.update(d.pop('backup', {}))
                    self.preview(o)
                else:
                    raise ValueError('Применить оформление: + / −')
            elif stage == 'preview':
                if text == '+':
                    o['stage'] = 'pack_type'
                    self.emit(o, 'pack-type', 'Что создаём?\n\n1. Стикер-пак\n2. Эмодзи-пак\n\nОтветьте цифрой.')
                elif text in {'-', '−'}:
                    self.emit(o, 'edit-result', 'Что изменить?\n!текст — ник\n!цвет — цвета\n!градиент — градиент\nВарианты эмодзи уже подтверждены.')
                else:
                    raise ValueError('Подтвердите результат: + / −. Или !текст, !цвет, !градиент.')
            else:
                self.emit(o, 'wait', 'Заказ сохранён. Обработка продолжается. !статус — текущий этап.')
        except ValueError as e:
            rev = d['rev']
            o.clear()
            o.update(original)
            o['data']['rev'] = rev
            if str(e).startswith('Превышен лимит выбора.') or stage in {'nick', 'nick_edit', 'text_value', 'editor_текст', 'editor_текст2'}:
                self.emit(o, 'invalid', str(e))
        o['data']['last_input'] = str(msgid)
        self.store.save(o)

    def help(self):
        return '💙【 Команды 】\n\nДо покупки и после:\n!команды - все команды\n!коллекции - каталог\n!пример - примеры\n!мои - ваши наборы\n!пак - ссылка на пак\n!файлы - старые архивы\n!бонус - баланс бонусов\n!бонус использовать 2 - потратить бонусы\n!статус - этап заказа\n!саппорт - обратиться в поддержку\n!продавец - позвать продавца\n\nВ вашем наборе:\n!корзина - выбранные эмодзи\n!добавить 1,3 - добавить варианты\n!убрать 2 - убрать вариант\n!смена - выбрать заново\n!готово - продолжить\n!текст - текст по номеру\n!текст2 - второй общий текст\n!назначить - распределить общие тексты\n!редактировать - открыть оформление\n!шрифт - изменить шрифт\n!цвет - изменить цвета\n!градиент - выбрать градиент\n!размер - размер текста\n!позиция - положение текста\n!поворот - наклон текста\n!обводка - контур текста\n!интервал - расстояние между буквами\n!предпросмотр - показать результат\n!сравнить - до и после\n!фон - проверить фон\n!откат - отменить изменение\n!сброс - сбросить оформление\n!копировать - перенести оформление\n!стиль - сохранить оформление\n!продолжить - повторить текущий шаг\n!бэк - запросить отмену\n!назад - предыдущий шаг\n!отмена - отменить текущую настройку\n!меню - все команды'

    def finish(self, o):
        if not getattr(self, 'can_deliver', lambda order: True)(o):
            raise RuntimeError('Статус оплаты изменился. Выдача остановлена для проверки.')
        d = o['data']
        if not d.get('pack_kind'):
            o['stage'] = 'pack_type'
            self.emit(o, 'pack-type', 'Что создаём?\n\n1. Стикер-пак\n2. Эмодзи-пак\n\nОтветьте цифрой.')
            self.store.save(o)
            return
        if d.get('pack_artifacts') and all((__import__('pathlib').Path(p).is_file() for p in [d['artifact_archive'], d['artifact_video'], *d['artifact_pages']])):
            from pathlib import Path
            pages = [Path(p) for p in d['artifact_pages']]
            video = Path(d['artifact_video'])
            archive = Path(d['artifact_archive'])
        else:
            o['data']['rev'] += 1
            pages, video, archive = self.render.build(o, True)
            d.update(pack_artifacts=True, artifact_archive=str(archive), artifact_video=str(video), artifact_pages=[str(p) for p in pages])
            self.store.save(o)
        if not getattr(self, 'can_deliver', lambda order: True)(o):
            raise RuntimeError('Статус оплаты изменился во время сборки. Выдача остановлена для проверки.')
        from .packs import links
        d['pack_urls'] = self.packs.publish(o, archive)
        self.store.save(o)
        if not getattr(self, 'can_deliver', lambda order: True)(self.store.get(o['id'])):
            raise RuntimeError('Статус оплаты изменился. Выдача остановлена для проверки.')
        url = self.link(o, video, archive)
        from .textflow import summary
        display_nick = summary(d) if d.get('individual_texts') else d['nick']
        unit = 'стикеров' if d['pack_kind'] == 'regular' else 'эмодзи'
        self.photos(o, 'final', pages)
        self.emit(o, 'ready', f"💙【 Ваши эмодзи готовы 】\n\nНик: {display_nick}\nВ наборе: {o['qty']} {unit}\n\n" + links(o) + f'\nАнимация: {url}\n\n!пак — повторить ссылку.')
        d = o['data']
        d['delivered_at'] = time.time()
        d['last_confirmation_contact'] = time.time()
        d['completion_version'] = 11
        if d.get('bonus_parent') or d.get('wallet_job'):
            d['bonus_expires'] = time.time() + 7 * 86400
            self.emit(o, 'bonus-ready', 'Ваши эмодзи готовы.\nДля повторного получения ссылки: !мои.')
        else:
            from .aftercare import Aftercare
            self.emit(o, 'completion', Aftercare(self.store, self).completion(o))
        d.update(artifact_archive=str(archive), artifact_video=str(video), artifact_pages=[str(p) for p in pages])
        o['stage'] = 'delivered'
        self.store.save(o)
        self.wallet.settle(o['id'], True)
