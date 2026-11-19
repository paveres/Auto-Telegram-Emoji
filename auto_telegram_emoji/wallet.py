__author__ = '@paveres'
__channel__ = 'https://t.me/g_plugins'
__contact__ = 'https://t.me/paveres'
import json, time

class Wallet:

    def __init__(self, store):
        self.store = store
        with store.tx() as db:
            db.executescript('CREATE TABLE IF NOT EXISTS bonus_ledger(key TEXT PRIMARY KEY,buyer INTEGER NOT NULL,delta INTEGER NOT NULL,reason TEXT,created REAL);\nCREATE TABLE IF NOT EXISTS bonus_reservations(oid TEXT PRIMARY KEY,buyer INTEGER NOT NULL,amount INTEGER NOT NULL,state TEXT NOT NULL);\nCREATE TABLE IF NOT EXISTS emoji_styles(buyer INTEGER PRIMARY KEY,data TEXT NOT NULL);')

    def credit(self, buyer, oid):
        old = self.store.get(oid)
        legacy = bool(old and old['data'].get('bonus_granted'))
        with self.store.tx() as db:
            added = bool(db.execute('INSERT OR IGNORE INTO bonus_ledger VALUES(?,?,?,?,?)', ('review:' + oid, buyer, 0 if legacy else 2, 'Бонус ранее выдан' if legacy else 'Отзыв об оплаченном заказе', time.time())).rowcount)
            return added and (not legacy)

    def balance(self, buyer):
        with self.store.tx() as db:
            earned = db.execute('SELECT COALESCE(SUM(delta),0) FROM bonus_ledger WHERE buyer=?', (buyer,)).fetchone()[0]
            reserved = db.execute("SELECT COALESCE(SUM(amount),0) FROM bonus_reservations WHERE buyer=? AND state='reserved'", (buyer,)).fetchone()[0]
            return earned - reserved

    def reserve(self, buyer, oid, amount):
        if not isinstance(amount, int) or not 1 <= amount <= 200:
            raise ValueError('Укажите от 1 до 200 бонусов.')
        with self.store.tx() as db:
            db.execute('BEGIN IMMEDIATE')
            old = db.execute('SELECT * FROM bonus_reservations WHERE oid=?', (oid,)).fetchone()
            if old:
                if old['buyer'] == buyer and old['amount'] == amount and (old['state'] in {'reserved', 'spent'}):
                    return
                raise ValueError('Для этого набора уже есть другое резервирование.')
            balance = db.execute('SELECT COALESCE(SUM(delta),0) FROM bonus_ledger WHERE buyer=?', (buyer,)).fetchone()[0] - db.execute("SELECT COALESCE(SUM(amount),0) FROM bonus_reservations WHERE buyer=? AND state='reserved'", (buyer,)).fetchone()[0]
            if balance < amount:
                raise ValueError('Недостаточно бонусов. Доступно: ' + str(balance))
            db.execute("INSERT INTO bonus_reservations VALUES(?,?,?,'reserved')", (oid, buyer, amount))

    def settle(self, oid, spend):
        with self.store.tx() as db:
            db.execute('BEGIN IMMEDIATE')
            r = db.execute("SELECT * FROM bonus_reservations WHERE oid=? AND state='reserved'", (oid,)).fetchone()
            if not r:
                return
            if spend:
                db.execute('INSERT OR IGNORE INTO bonus_ledger VALUES(?,?,?,?,?)', ('spend:' + oid, r['buyer'], -r['amount'], 'Готовый бонусный набор', time.time()))
            db.execute('UPDATE bonus_reservations SET state=? WHERE oid=?', ('spent' if spend else 'released', oid))

    def history(self, buyer):
        with self.store.tx() as db:
            return [dict(r) for r in db.execute('SELECT delta,reason,created FROM bonus_ledger WHERE buyer=? ORDER BY created DESC LIMIT 10', (buyer,))]

    def style(self, buyer, data=None):
        with self.store.tx() as db:
            if data is not None:
                db.execute('INSERT OR REPLACE INTO emoji_styles VALUES(?,?)', (buyer, json.dumps(data)))
                return
            row = db.execute('SELECT data FROM emoji_styles WHERE buyer=?', (buyer,)).fetchone()
            return json.loads(row[0]) if row else None
