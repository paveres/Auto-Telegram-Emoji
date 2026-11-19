__author__ = '@paveres'
__channel__ = 'https://t.me/g_plugins'
__contact__ = 'https://t.me/paveres'
from contextlib import contextmanager
from pathlib import Path
import sqlite3
import time
import json
FINISHED = {'COMPLETED', 'REFUNDED', 'CANCELLED'}
HOLD = {'PARKED', 'REVIEW', 'RENT_UNKNOWN', 'REFUND_UNKNOWN', 'SUBMIT_UNKNOWN'}

class OrderQueue:

    def __init__(self, root):
        self.root = Path(root)
        self.path = Path(root) / 'data/queue.sqlite3'
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.db() as db:
            db.executescript('CREATE TABLE IF NOT EXISTS jobs(\n                seq INTEGER PRIMARY KEY AUTOINCREMENT,order_id TEXT UNIQUE NOT NULL,\n                plugin TEXT NOT NULL,buyer INTEGER NOT NULL,stage TEXT NOT NULL,\n                slot INTEGER NOT NULL DEFAULT 0,done INTEGER NOT NULL DEFAULT 0,created REAL NOT NULL);\n                CREATE INDEX IF NOT EXISTS buyer_fifo ON jobs(buyer,done,seq);')
        self.path.chmod(384)

    def limit(self):
        try:
            return max(0, int(json.loads((self.root / 'config/app.json').read_text()).get('max_active', 2)))
        except (OSError, ValueError, TypeError):
            return 2

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=20)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('PRAGMA busy_timeout=20000')
        try:
            db.execute('BEGIN IMMEDIATE')
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def sync(self, plugin, orders):
        with self.db() as db:
            for o in orders:
                db.execute('INSERT OR IGNORE INTO jobs(order_id,plugin,buyer,stage,created) VALUES(?,?,?,?,?)', (o['id'], plugin, o['buyer'], o['stage'], o['data'].get('accepted_at', o['updated'])))
                row = db.execute('SELECT plugin,buyer FROM jobs WHERE order_id=?', (o['id'],)).fetchone()
                if row['plugin'] != plugin or row['buyer'] != o['buyer']:
                    raise ValueError('Order queue identity mismatch')
                done = o['stage'] in FINISHED
                db.execute('UPDATE jobs SET stage=?,done=?,slot=CASE WHEN ? THEN 0 ELSE slot END WHERE order_id=?', (o['stage'], int(done), int(done or o['stage'] in HOLD), o['id']))

    def claim(self, plugin, order):
        limit = self.limit()
        with self.db() as db:
            row = db.execute('SELECT * FROM jobs WHERE order_id=? AND plugin=?', (order['id'], plugin)).fetchone()
            if not row or row['done'] or row['stage'] in HOLD:
                return False
            if db.execute("SELECT 1 FROM jobs WHERE buyer=? AND done=0 AND stage NOT IN ('RUNNING','COMPLETED','REFUNDED','CANCELLED') AND seq<?", (row['buyer'], row['seq'])).fetchone():
                return False
            if row['slot']:
                return True
            if limit and db.execute('SELECT COUNT(*) FROM jobs WHERE slot=1 AND done=0').fetchone()[0] >= limit:
                return False
            available = db.execute("SELECT j.* FROM jobs j WHERE j.done=0 AND j.slot=0\n                AND NOT EXISTS(SELECT 1 FROM jobs old WHERE old.buyer=j.buyer AND old.done=0 AND old.stage NOT IN ('RUNNING','COMPLETED','REFUNDED','CANCELLED') AND old.seq<j.seq)\n                ORDER BY j.seq").fetchall()
            first = next((r for r in available if r['stage'] not in HOLD), None)
            if limit and (not first or first['order_id'] != row['order_id']):
                return False
            db.execute('UPDATE jobs SET slot=1 WHERE order_id=?', (row['order_id'],))
            return True

    def current(self, buyer):
        with self.db() as db:
            row = db.execute("SELECT * FROM jobs WHERE buyer=? AND done=0 AND stage NOT IN ('RUNNING','COMPLETED','REFUNDED','CANCELLED') ORDER BY seq LIMIT 1", (buyer,)).fetchone()
            if not row:
                row = db.execute('SELECT * FROM jobs WHERE buyer=? AND done=0 ORDER BY seq DESC LIMIT 1', (buyer,)).fetchone()
            if not row:
                row = db.execute('SELECT * FROM jobs WHERE buyer=? ORDER BY seq DESC LIMIT 1', (buyer,)).fetchone()
            return dict(row) if row else None

    def preceding(self, buyer, order_id):
        with self.db() as db:
            row = db.execute('SELECT seq FROM jobs WHERE order_id=?', (order_id,)).fetchone()
            if not row:
                return []
            return [dict(r) for r in db.execute("SELECT * FROM jobs WHERE buyer=? AND done=0 AND stage NOT IN ('RUNNING','COMPLETED','REFUNDED','CANCELLED') AND seq<? ORDER BY seq", (buyer, row['seq']))]

    def position(self, order_id):
        limit = self.limit()
        if not limit:
            return 0
        with self.db() as db:
            row = db.execute('SELECT * FROM jobs WHERE order_id=?', (order_id,)).fetchone()
            if not row or row['done'] or row['slot']:
                return 0
            waiting = [r['order_id'] for r in db.execute("SELECT j.* FROM jobs j WHERE j.done=0 AND j.slot=0 AND NOT EXISTS(SELECT 1 FROM jobs old WHERE old.buyer=j.buyer AND old.done=0 AND old.stage NOT IN ('RUNNING','COMPLETED','REFUNDED','CANCELLED') AND old.seq<j.seq) ORDER BY j.seq") if r['stage'] not in HOLD]
            if order_id not in waiting:
                return 0
            free = max(0, limit - db.execute('SELECT COUNT(*) FROM jobs WHERE slot=1 AND done=0').fetchone()[0])
            return max(0, waiting.index(order_id) + 1 - free)
