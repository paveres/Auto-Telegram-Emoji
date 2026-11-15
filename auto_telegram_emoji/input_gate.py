__author__ = '@justmeth'
__channel__ = 'https://t.me/g_plugins'
__contact__ = 'https://t.me/justmeth'
import time
SAFE = {'!меню', '!статус', '!продавец', '!саппорт'}

class InputGate:

    def __init__(self, store):
        self.s = store
        with store.tx() as db:
            db.executescript('CREATE TABLE IF NOT EXISTS emoji_input_gate(buyer INTEGER PRIMARY KEY,oid TEXT,busy INTEGER DEFAULT 0,floor INTEGER DEFAULT 0); CREATE TABLE IF NOT EXISTS emoji_command_limits(buyer INTEGER PRIMARY KEY,window REAL,count INTEGER,heavy REAL);')

    def begin(self, o):
        with self.s.tx() as db:
            db.execute('INSERT INTO emoji_input_gate VALUES(?,?,1,0) ON CONFLICT(buyer) DO UPDATE SET oid=excluded.oid,busy=1', (o['buyer'], o['id']))

    def delivered(self, o):
        with self.s.tx() as db:
            if db.execute("SELECT 1 FROM outbox WHERE oid=? AND state!='sent' LIMIT 1", (o['id'],)).fetchone():
                return
            floor = db.execute("SELECT COALESCE(MAX(CAST(remote AS INTEGER)),0) FROM outbox WHERE oid=? AND state='sent'", (o['id'],)).fetchone()[0]
            db.execute('UPDATE emoji_input_gate SET busy=0,floor=MAX(floor,?) WHERE buyer=? AND oid=?', (floor, o['buyer'], o['id']))

    def accepts(self, buyer, msgid, command):
        if command in SAFE:
            return True
        with self.s.tx() as db:
            row = db.execute('SELECT * FROM emoji_input_gate WHERE buyer=?', (buyer,)).fetchone()
        return not row or (not row['busy'] and int(msgid) > row['floor'])

    def rate(self, buyer, heavy=False):
        now = time.time()
        with self.s.tx() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM emoji_command_limits WHERE buyer=?', (buyer,)).fetchone()
            window, count, last = (row['window'], row['count'], row['heavy']) if row else (now, 0, 0)
            if now - window >= 10:
                window, count = (now, 0)
            if count >= 10 or (heavy and now - last < 4):
                return False
            db.execute('INSERT OR REPLACE INTO emoji_command_limits VALUES(?,?,?,?)', (buyer, window, count + 1, now if heavy else last))
            return True
