__author__ = '@paveres'
__channel__ = 'https://t.me/g_plugins'
__contact__ = 'https://t.me/paveres'
import sqlite3, json, time
from contextlib import contextmanager
from pathlib import Path

class Store:

    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.tx() as db:
            db.executescript("PRAGMA journal_mode=WAL;\nCREATE TABLE IF NOT EXISTS orders(id TEXT PRIMARY KEY,buyer INTEGER,chat TEXT,qty INTEGER,stage TEXT,data TEXT,created REAL);\nCREATE TABLE IF NOT EXISTS inbox(key TEXT PRIMARY KEY,buyer INTEGER,text TEXT,state TEXT DEFAULT 'pending',created REAL);\nCREATE TABLE IF NOT EXISTS outbox(key TEXT PRIMARY KEY,oid TEXT,kind TEXT,payload TEXT,state TEXT DEFAULT 'pending',remote TEXT);\nCREATE TABLE IF NOT EXISTS links(token TEXT PRIMARY KEY,oid TEXT,active INTEGER,video TEXT,archive TEXT);\n")

    @contextmanager
    def tx(self):
        db = sqlite3.connect(self.path, timeout=20)
        db.row_factory = sqlite3.Row
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def decode(self, r):
        if not r:
            return None
        o = dict(r)
        o['data'] = json.loads(o['data'])
        o['paid_qty'] = 0 if o['data'].get('wallet_job') else o['qty']
        o['qty'] += int(o['data'].get('bonus_qty', 0)) + int(o['data'].get('wallet_bonus_qty', 0))
        return o

    def get(self, oid):
        with self.tx() as db:
            return self.decode(db.execute('SELECT * FROM orders WHERE id=?', (oid,)).fetchone())

    def all(self):
        with self.tx() as db:
            return [self.decode(r) for r in db.execute('SELECT * FROM orders ORDER BY created')]

    def save(self, o):
        with self.tx() as db:
            db.execute("UPDATE orders SET stage=?,data=? WHERE id=? AND stage NOT IN ('CLOSED','REFUNDED','CANCELLED')", (o['stage'], json.dumps(o['data'], ensure_ascii=False), o['id']))

    def add(self, oid, buyer, chat, qty):
        with self.tx() as db:
            db.execute('INSERT OR IGNORE INTO orders VALUES(?,?,?,?,?,?,?)', (oid, buyer, str(chat), qty, 'collection', json.dumps({'cart': [], 'rev': 0, 'nick': '', 'color': 0, 'gradient': 0, 'generation': 0}), time.time()))

    def enqueue(self, key, buyer, text):
        with self.tx() as db:
            db.execute('INSERT OR IGNORE INTO inbox(key,buyer,text,created) VALUES(?,?,?,?)', (str(key), buyer, text, time.time()))

    def emit(self, o, key, text, kind='text'):
        if kind == 'text' and (len(str(text)) > 800 or len(str(text).splitlines()) > 8):
            parts = []
            lines = []
            for line in str(text).splitlines():
                if lines and (len(lines) >= 8 or len('\n'.join(lines)) + len(line) > 800):
                    parts.append('\n'.join(lines))
                    lines = []
                lines.append(line)
            if lines:
                parts.append('\n'.join(lines))
            for i, piece in enumerate(parts):
                self.emit(o, key + ':part' + str(i), piece, kind)
            return
        with self.tx() as db:
            db.execute('INSERT OR IGNORE INTO outbox(key,oid,kind,payload) VALUES(?,?,?,?)', (o['id'] + ':' + str(o['data'].get('rev', 0)) + ':' + key, o['id'], kind, str(text)))

    def close(self, oid, stage):
        with self.tx() as db:
            db.execute('UPDATE orders SET stage=? WHERE id=?', (stage, oid))
            db.execute('UPDATE links SET active=0 WHERE oid=?', (oid,))

    def patch(self, oid, **changes):
        with self.tx() as db:
            row = db.execute('SELECT data FROM orders WHERE id=?', (oid,)).fetchone()
            if row:
                data = json.loads(row['data'])
                data.update(changes)
                db.execute('UPDATE orders SET data=? WHERE id=?', (json.dumps(data, ensure_ascii=False), oid))

    def event(self, o, key, text):
        copy = dict(o)
        copy['data'] = {**o['data'], 'rev': 'event'}
        self.emit(copy, key, text)
