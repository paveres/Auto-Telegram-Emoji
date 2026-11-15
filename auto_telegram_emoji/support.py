__author__ = '@justmeth'
__channel__ = 'https://t.me/g_plugins'
__contact__ = 'https://t.me/justmeth'
import hashlib, time, math
from .aliases import normalize
REASONS = ['Не нравится текст или есть опечатка', 'Расположение или размер текста', 'Цвет, градиент или шрифт', 'Не скачивается архив или не открываются файлы', 'Результат не соответствует выбранным вариантам', 'Другое']

class Support:

    def __init__(self, adapter):
        self.a = adapter
        self.s = adapter.store
        with self.s.tx() as db:
            db.execute("CREATE TABLE IF NOT EXISTS emoji_support(id TEXT PRIMARY KEY,buyer INTEGER,chat TEXT,oid TEXT,reason TEXT,details TEXT,created REAL,state TEXT DEFAULT 'pending',remote TEXT)")

    def handle(self, p, text, key, active):
        raw = text
        text = normalize(text, p['stage'])
        stage = p['stage']
        d = p['data']
        s = self.s
        if stage == 'support_details' and (not raw.startswith(('!', '/'))):
            text = raw.strip()
        if text != '!саппорт' and (not stage.startswith('support_')):
            return False
        d['rev'] = key

        def say(label, message):
            s.emit(p, 'support-' + label, message)
        if text in {'!назад', '!отмена', '!продолжить'}:
            p['stage'] = 'public'
            say('cancel', 'Обращение не отправлено. Заказ сохранён. !продолжить — вернуться к заказу.')
        elif text == '!саппорт':
            with s.tx() as db:
                last = db.execute('SELECT MAX(created) FROM emoji_support WHERE buyer=?', (p['buyer'],)).fetchone()[0]
            if last and time.time() - last < 86400:
                hours = math.ceil((last + 86400 - time.time()) / 3600)
                say('limit', f'Ваш запрос уже зарегистрирован. Следующий можно отправить через {hours} ч. Ответ будет в этом чате. !отмена — вернуться к заказу.')
            else:
                p['stage'] = 'support_reason'
                orders = [o for o in s.all() if o['buyer'] == p['buyer'] and o['data'].get('kind') not in {'public', 'archive'}]
                d['support_order'] = active['id'] if active else orders[-1]['id'] if orders else ''
                say('reasons', 'Хотите обратиться в поддержку? Выберите причину:\n\n' + '\n'.join((f'{i}. {reason}' for i, reason in enumerate(REASONS, 1))) + '\n\nНапишите номер. !отмена — выйти без отправки.')
        elif stage == 'support_reason':
            if not text.isdigit() or not 1 <= int(text) <= len(REASONS):
                say('reason-error', 'Выберите причину: число 1–6. !отмена — выйти.')
            else:
                d['support_reason'] = REASONS[int(text) - 1]
                p['stage'] = 'support_details'
                say('details', 'Опишите проблему как можно подробнее, чтобы я быстрее помог.\nЧто получилось и что вы хотите изменить? Для текста укажите нужную надпись, расположение, размер и номера эмодзи. Для файлов — что именно не открывается и какая ошибка.\nПри желании укажите номер своего заказа. Не присылайте пароли и коды входа.\nОтправьте описание одним сообщением, от 10 до 2000 символов. !отмена — выйти.')
        elif stage == 'support_details':
            if text.startswith('!'):
                say('details-command', 'Сейчас нужно описание проблемы обычным текстом. !отмена — выйти; !меню — список команд.')
            elif not 10 <= len(text) <= 2000:
                say('details-length', 'Опишите проблему одним сообщением: от 10 до 2000 символов.')
            else:
                d['support_details'] = text
                p['stage'] = 'support_confirm'
                say('confirm', 'Проверьте обращение.\nЗаказ: ' + (d.get('support_order') or 'не выбран') + '\nПричина: ' + d['support_reason'] + '\n\n' + text + '\n\nОтправить в поддержку? Да / нет. После отправки новый запрос доступен через 24 часа.')
        elif stage == 'support_confirm':
            if text == '-':
                p['stage'] = 'support_details'
                say('edit', 'Введите исправленное описание. Запрос ещё не отправлен. !отмена — выйти.')
            elif text == '+':
                ticket = hashlib.sha256((str(p['buyer']) + key).encode()).hexdigest()[:10].upper()
                now = time.time()
                with s.tx() as db:
                    db.execute('BEGIN IMMEDIATE')
                    last = db.execute('SELECT MAX(created) FROM emoji_support WHERE buyer=?', (p['buyer'],)).fetchone()[0]
                    if last and now - last < 86400:
                        say_limit = True
                    else:
                        db.execute("INSERT OR IGNORE INTO emoji_support VALUES(?,?,?,?,?,?,?,'pending',NULL)", (ticket, p['buyer'], p['chat'], d.get('support_order', ''), d['support_reason'], d['support_details'], now))
                        say_limit = False
                p['stage'] = 'public'
                say('submitted', 'Запрос уже зарегистрирован. Следующее обращение — через 24 часа.' if say_limit else 'Обращение №' + ticket + ' зарегистрировано. Ответим в этом чате FunPay. Повторный запрос можно отправить через 24 часа.')
            else:
                say('answer', 'Отправить обращение? Да / нет. !отмена — выйти.')
        s.save(p)
        self.a.transport.flush(p)
        return True

    def deliver(self):
        from auto_telegram_emoji.platform import emoji, escape_html
        tg = getattr(self.a.k, 'telegram', None)
        if not tg:
            return
        with self.s.tx() as db:
            rows = [dict(r) for r in db.execute("SELECT * FROM emoji_support WHERE state='pending' ORDER BY created LIMIT 3")]
        for row in rows:
            with self.s.tx() as db:
                if not db.execute("UPDATE emoji_support SET state='sending' WHERE id=? AND state='pending'", (row['id'],)).rowcount:
                    continue
            text = emoji('info') + ' <b>Обращение по эмодзи №' + row['id'] + '</b>\nПокупатель: <code>' + str(row['buyer']) + '</code>\nЧат: https://funpay.com/chat/?node=' + str(row['chat']) + '\nЗаказ: ' + escape_html(row['oid'] or 'не выбран') + '\nПричина: ' + escape_html(row['reason']) + '\n\n' + escape_html(row['details'])
            try:
                ids = []
                for owner in tg.authorized_users:
                    ids.append(tg.bot.send_message(owner, text, parse_mode='HTML', disable_web_page_preview=True).message_id)
                if not ids:
                    raise RuntimeError('No support recipients')
                with self.s.tx() as db:
                    db.execute("UPDATE emoji_support SET state='sent',remote=? WHERE id=?", (','.join(map(str, ids)), row['id']))
            except Exception:
                with self.s.tx() as db:
                    db.execute("UPDATE emoji_support SET state='uncertain' WHERE id=?", (row['id'],))
                self.a.alert('support:' + row['id'], 'Неизвестный результат доставки обращения; требуется проверка Telegram.')
