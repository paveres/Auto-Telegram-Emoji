__author__ = '@paveres'
__channel__ = 'https://t.me/g_plugins'
__contact__ = 'https://t.me/paveres'
import json
from auto_telegram_emoji.order_queue import OrderQueue, HOLD

class EmojiQueue(OrderQueue):

    def limit(self):
        try:
            return max(1, min(10, int(json.loads((self.root / 'config/app.json').read_text()).get('max_active', 10))))
        except (OSError, ValueError, TypeError):
            return 10

    def claim(self, plugin, order):
        with self.db() as db:
            row = db.execute('SELECT * FROM jobs WHERE order_id=? AND plugin=?', (order['id'], plugin)).fetchone()
            if not row or row['done'] or row['stage'] in HOLD:
                return False
            if db.execute("SELECT 1 FROM jobs WHERE buyer=? AND done=0 AND seq<? AND stage NOT IN ('RUNNING','COMPLETED','REFUNDED','CANCELLED')", (row['buyer'], row['seq'])).fetchone():
                return False
            if row['slot']:
                return True
            if db.execute('SELECT COUNT(*) FROM jobs WHERE plugin=? AND slot=1 AND done=0', (plugin,)).fetchone()[0] >= self.limit():
                return False
            candidates = db.execute("SELECT j.order_id FROM jobs j WHERE plugin=? AND done=0 AND slot=0 AND stage NOT IN ('REVIEW','PARKED','RENT_UNKNOWN','REFUND_UNKNOWN','SUBMIT_UNKNOWN') AND NOT EXISTS(SELECT 1 FROM jobs p WHERE p.buyer=j.buyer AND p.seq<j.seq AND p.done=0 AND p.stage NOT IN ('RUNNING','COMPLETED','REFUNDED','CANCELLED')) ORDER BY seq", (plugin,)).fetchall()
            if not candidates or candidates[0]['order_id'] != row['order_id']:
                return False
            db.execute('UPDATE jobs SET slot=1 WHERE order_id=?', (row['order_id'],))
            return True

    def position(self, order_id):
        with self.db() as db:
            row = db.execute('SELECT * FROM jobs WHERE order_id=?', (order_id,)).fetchone()
            if not row or row['done'] or row['slot']:
                return 0
            rows = db.execute('SELECT order_id FROM jobs WHERE plugin=? AND done=0 AND slot=0 ORDER BY seq', (row['plugin'],)).fetchall()
            return 1 + [x[0] for x in rows].index(order_id)
