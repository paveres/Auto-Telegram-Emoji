__author__ = '@justmeth'
__channel__ = 'https://t.me/g_plugins'
__contact__ = 'https://t.me/justmeth'
import gzip, json, re, secrets, threading, time, zipfile
from pathlib import Path
import requests
_UPLOAD = threading.Lock()

class PackPending(RuntimeError):

    def __init__(self, delay=30):
        self.delay = max(3, int(delay))
        super().__init__('Telegram upload pending')

class PackError(RuntimeError):
    pass

class Telegram:

    def __init__(self, token):
        self.url = 'https://api.telegram.org/bot' + token + '/'
        self.session = requests.Session()

    def call(self, method, data=None, files=None, missing=False):
        try:
            response = self.session.post(self.url + method, data=data or {}, files=files, timeout=(10, 60))
            result = response.json()
        except (requests.RequestException, ValueError):
            raise PackPending() from None
        if result.get('ok'):
            return result['result']
        code = result.get('error_code', response.status_code)
        if code == 429:
            raise PackPending(result.get('parameters', {}).get('retry_after', 60))
        if code >= 500:
            raise PackPending()
        description = str(result.get('description', ''))
        if missing and code == 400 and ('STICKERSET_INVALID' in description.upper()):
            return None
        raise PackError('Telegram rejected ' + method + ' (' + str(code) + ')')

class Packs:

    def __init__(self, root, store, api=None, owner=None, username=None):
        self.root = Path(root)
        self.store = store
        self.api = api
        self.owner = owner
        self.username = username
        with store.tx() as db:
            db.executescript('\nCREATE TABLE IF NOT EXISTS emoji_packs(number INTEGER PRIMARY KEY AUTOINCREMENT,oid TEXT NOT NULL,part INTEGER NOT NULL,kind TEXT NOT NULL,name TEXT NOT NULL UNIQUE,items TEXT NOT NULL,complete INTEGER NOT NULL DEFAULT 0,UNIQUE(oid,part));\n')

    def connect(self):
        if self.api is None:
            try:
                from .settings import credentials
                cfg = credentials(self.root)
                self.owner = int(cfg['owner_id'])
                self.api = Telegram(cfg['token'])
            except (OSError, ValueError, KeyError):
                raise PackError('Pack bot configuration unavailable') from None
        if not self.username:
            self.username = self.api.call('getMe')['username']
        if not re.fullmatch('[A-Za-z0-9_]{5,32}', self.username):
            raise PackError('Invalid pack bot username')

    def rows(self, oid):
        with self.store.tx() as db:
            return [dict(r) for r in db.execute('SELECT * FROM emoji_packs WHERE oid=? ORDER BY part', (oid,))]

    def save(self, row, items, complete=False):
        with self.store.tx() as db:
            db.execute('UPDATE emoji_packs SET items=?,complete=? WHERE number=?', (json.dumps(items), int(complete), row['number']))

    def publish(self, o, archive):
        if not _UPLOAD.acquire(blocking=False):
            raise PackPending(5)
        try:
            return self._publish(o, archive)
        finally:
            _UPLOAD.release()

    def _publish(self, o, archive):
        self.connect()
        kind = o['data'].get('pack_kind')
        if kind not in {'regular', 'custom_emoji'}:
            raise PackError('Pack type is missing')
        with zipfile.ZipFile(archive) as z:
            entries = z.infolist()
            if len(entries) != o['qty'] or not 1 <= len(entries) <= 200:
                raise PackError('Pack contents mismatch')
            raws = []
            for item in entries:
                if not item.filename.endswith('.tgs') or item.file_size > 512 * 1024:
                    raise PackError('Invalid animation file')
                raw = z.read(item)
                try:
                    import zlib
                    dec = zlib.decompressobj(16 + zlib.MAX_WBITS)
                    payload = dec.decompress(raw, 4 * 1024 * 1024 + 1)
                    if len(payload) > 4 * 1024 * 1024 or not dec.eof:
                        raise ValueError()
                    animation = json.loads(payload)
                    if animation.get('w') != 512 or animation.get('h') != 512 or (not 0 < (animation['op'] - animation.get('ip', 0)) / animation['fr'] <= 3):
                        raise ValueError()
                    raw = gzip.compress(payload, compresslevel=9, mtime=0)
                    if len(raw) > 65536:
                        raise ValueError()
                except (ValueError, KeyError, TypeError, ZeroDivisionError, zlib.error):
                    raise PackError('Animation exceeds Telegram limits') from None
                raws.append(raw)
        limit = 120 if kind == 'regular' else 200
        for part, start in enumerate(range(0, len(raws), limit)):
            with self.store.tx() as db:
                row = db.execute('SELECT * FROM emoji_packs WHERE oid=? AND part=?', (o['id'], part)).fetchone()
                if row is None:
                    for attempt in range(20):
                        code = secrets.choice('abcdefghijklmnopqrstuvwxyz') + ''.join((secrets.choice('abcdefghijklmnopqrstuvwxyz0123456789') for _ in range(5)))
                        name = code + '_by_' + self.username
                        if not db.execute('SELECT 1 FROM emoji_packs WHERE name=?', (name,)).fetchone():
                            break
                    else:
                        raise PackError('Could not reserve a pack name')
                    db.execute('INSERT INTO emoji_packs(oid,part,kind,name,items) VALUES(?,?,?,?,?)', (o['id'], part, kind, name, '[]'))
                    row = db.execute('SELECT * FROM emoji_packs WHERE oid=? AND part=?', (o['id'], part)).fetchone()
                row = dict(row)
            if row['kind'] != kind:
                raise PackError('Pack type changed after creation')
            batch = raws[start:start + limit]
            items = json.loads(row['items'])
            remote = self.api.call('getStickerSet', {'name': row['name']}, missing=True)
            count = len(remote['stickers']) if remote else 0
            if remote and (remote['sticker_type'] != kind or count > len(batch) or count > len(items)):
                raise PackError('Unexpected pack contents')
            for index, raw in enumerate(batch):
                if index < count:
                    continue
                if index >= len(items):
                    file = self.api.call('uploadStickerFile', {'user_id': self.owner, 'sticker_format': 'animated'}, files={'sticker': ('emoji.tgs', raw, 'application/x-tgsticker')})
                    items.append({'sticker': file['file_id'], 'format': 'animated', 'emoji_list': ['💙']})
                    self.save(row, items)
                if index == 0 and remote is None:
                    self.api.call('createNewStickerSet', {'user_id': self.owner, 'name': row['name'], 'title': '#' + str(row['number']), 'sticker_type': kind, 'stickers': json.dumps([items[index]])})
                else:
                    self.api.call('addStickerToSet', {'user_id': self.owner, 'name': row['name'], 'sticker': json.dumps(items[index])})
                remote = self.api.call('getStickerSet', {'name': row['name']})
                count = len(remote['stickers'])
                if count != index + 1 or remote['sticker_type'] != kind:
                    raise PackError('Telegram pack verification failed')
            if count != len(batch):
                raise PackError('Incomplete Telegram pack')
            self.save(row, items, True)
        return ['https://t.me/' + ('addstickers/' if kind == 'regular' else 'addemoji/') + row['name'] for row in self.rows(o['id'])]

def links(o):
    return '\n'.join(('Пак: ' + url for url in o['data'].get('pack_urls', [])))
