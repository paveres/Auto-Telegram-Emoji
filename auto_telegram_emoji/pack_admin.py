__author__ = '@paveres'
__channel__ = 'https://t.me/g_plugins'
__contact__ = 'https://t.me/paveres'
import html, json, logging, re, sqlite3, time
from pathlib import Path
from .packs import Telegram, PackPending, PackError
LOG = logging.getLogger('auto_telegram_emoji.pack_admin')

def button(text, callback=None, url=None, icon=None):
    b = {'text': text}
    if callback:
        b['callback_data'] = callback
    if url:
        b['url'] = url
    if icon:
        b['icon_custom_emoji_id'] = icon
    return b

class Admin:

    def __init__(self, root, api=None, owner=None):
        self.root = Path(root)
        if api is None:
            from .settings import credentials
            cfg = credentials(self.root)
            api = Telegram(cfg['token'])
            owner = int(cfg['owner_id'])
        self.api = api
        self.owner = owner
        self.path = self.root / 'data/orders.sqlite3'

    def query(self, sql, params=(), one=False):
        with sqlite3.connect('file:' + self.path.as_posix() + '?mode=ro', uri=True, timeout=15) as db:
            db.row_factory = sqlite3.Row
            cursor = db.execute(sql, params)
            return cursor.fetchone() if one else cursor.fetchall()

    def screen(self, data='admin:home'):
        back = [button('◁ Назад', 'admin:home')]
        if data == 'admin:home':
            return ('<b><tg-emoji emoji-id="5870528606328852614">📁</tg-emoji> Паки</b>', [[button('Созданные паки', 'admin:list:0', icon='5870528606328852614')]])
        match = re.fullmatch('admin:list:(\\d{1,6})', data)
        if match:
            total = self.query('SELECT COUNT(*) FROM emoji_packs', one=True)[0]
            page = min(int(match[1]), max(0, (total - 1) // 8))
            rows = self.query('SELECT number,kind,complete FROM emoji_packs ORDER BY number DESC LIMIT 8 OFFSET ?', (page * 8,))
            keyboard = [[button('#' + str(r['number']) + ' · ' + ('Стикеры' if r['kind'] == 'regular' else 'Эмодзи'), 'admin:pack:' + str(r['number']), icon='6035128606563241721')] for r in rows]
            nav = []
            if page:
                nav.append(button('◁ Назад', 'admin:list:' + str(page - 1)))
            if (page + 1) * 8 < total:
                nav.append(button('Далее ▷', 'admin:list:' + str(page + 1)))
            if nav:
                keyboard.append(nav)
            keyboard.append(back)
            return ('<b>Созданные паки</b>\n\nВсего: ' + str(total) + '\nСтраница: ' + str(page + 1), keyboard)
        match = re.fullmatch('admin:pack:(\\d{1,12})', data)
        if match:
            row = self.query('SELECT * FROM emoji_packs WHERE number=?', (int(match[1]),), one=True)
            if row:
                order = self.query('SELECT data FROM orders WHERE id=?', (row['oid'],), one=True)
                nick = json.loads(order['data']).get('nick', '') if order else ''
                text = '<b>#' + str(row['number']) + '</b>\n\nТип: ' + ('Стикер-пак' if row['kind'] == 'regular' else 'Эмодзи-пак') + '\nЭлементов: ' + str(len(json.loads(row['items']))) + '\nСтатус: ' + ('Готов' if row['complete'] else 'Создаётся') + '\nЗаказ: ' + html.escape(row['oid'])
                if nick:
                    text += '\nТекст: ' + html.escape(nick)
                keyboard = []
                if row['complete']:
                    keyboard.append([button('Открыть пак', url='https://t.me/' + ('addstickers/' if row['kind'] == 'regular' else 'addemoji/') + row['name'], icon='5769289093221454192')])
                keyboard.extend([[button('Обновить', data, icon='5345906554510012647')], [button('◁ Назад', 'admin:list:0')]])
                return (text, keyboard)
        return self.screen()

    def handle(self, update):
        callback = update.get('callback_query')
        message = (callback or {}).get('message') or update.get('message') or {}
        sender = (callback or message).get('from', {})
        chat = message.get('chat', {})
        if sender.get('id') != self.owner or chat.get('id') != self.owner or chat.get('type') != 'private':
            return False
        if callback:
            data = callback.get('data', '')
            if not re.fullmatch('admin:(?:home|list:\\d{1,6}|pack:\\d{1,12})', data):
                return False
            text, keyboard = self.screen(data)
            self.api.call('answerCallbackQuery', {'callback_query_id': callback['id']})
            try:
                self.api.call('editMessageText', {'chat_id': self.owner, 'message_id': message['message_id'], 'text': text, 'parse_mode': 'HTML', 'reply_markup': json.dumps({'inline_keyboard': keyboard})})
            except PackError:
                pass
        else:
            if message.get('text', '').split(' ', 1)[0] not in {'/start', '/menu'}:
                return False
            text, keyboard = self.screen()
            self.api.call('sendMessage', {'chat_id': self.owner, 'text': text, 'parse_mode': 'HTML', 'reply_markup': json.dumps({'inline_keyboard': keyboard})})
        return True

    def run(self):
        offset_file = self.path.parent / 'pack-admin-offset.json'
        offset = int(json.loads(offset_file.read_text()).get('offset', 0)) if offset_file.exists() else 0
        while True:
            try:
                updates = self.api.call('getUpdates', {'offset': offset, 'timeout': 25, 'allowed_updates': json.dumps(['message', 'callback_query'])})
                for update in updates:
                    self.handle(update)
                    offset = update['update_id'] + 1
                    tmp = offset_file.with_suffix('.tmp')
                    tmp.write_text(json.dumps({'offset': offset}))
                    tmp.chmod(384)
                    tmp.replace(offset_file)
            except PackPending as error:
                time.sleep(min(error.delay, 3600))
            except Exception as error:
                LOG.warning('Pack admin retry: %s', type(error).__name__)
                time.sleep(10)
if __name__ == '__main__':
    Admin(Path.cwd()).run()
