__author__ = '@justmeth'
__channel__ = 'https://t.me/g_plugins'
__contact__ = 'https://t.me/justmeth'
from contextlib import contextmanager
from pathlib import Path
import functools, re, sqlite3, time

class ReviewRegistry:

    def __init__(self, root):
        self.path = Path(root) / 'data/reviews.sqlite3'
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.db() as db:
            db.executescript('CREATE TABLE IF NOT EXISTS reviews(order_id TEXT PRIMARY KEY,buyer INTEGER NOT NULL,stars INTEGER NOT NULL,created REAL NOT NULL); CREATE INDEX IF NOT EXISTS reviewer ON reviews(buyer); CREATE TABLE IF NOT EXISTS chats(chat TEXT PRIMARY KEY,buyer INTEGER NOT NULL);')
        self.path.chmod(384)

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=20)
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('PRAGMA busy_timeout=20000')
        try:
            with db:
                yield db
        finally:
            db.close()

    def mark(self, buyer, order_id, stars=None):
        stars = 0 if stars is None else int(stars)
        if type(buyer) is not int or buyer <= 0 or stars not in {0, 1, 2, 3, 4, 5}:
            return False
        with self.db() as db:
            return bool(db.execute('INSERT OR IGNORE INTO reviews VALUES(?,?,?,?)', (str(order_id), buyer, int(stars), time.time())).rowcount)

    def known(self, buyer):
        with self.db() as db:
            return bool(db.execute('SELECT 1 FROM reviews WHERE buyer=? LIMIT 1', (buyer,)).fetchone())

    def bind(self, chat, buyer):
        if chat is None or type(buyer) is not int or buyer <= 0:
            return
        with self.db() as db:
            db.execute('INSERT OR REPLACE INTO chats VALUES(?,?)', (str(chat), buyer))

    def buyer(self, chat, owner=None):
        with self.db() as db:
            row = db.execute('SELECT buyer FROM chats WHERE chat=?', (str(chat),)).fetchone()
        if row:
            return row[0]
        match = re.fullmatch('users-(\\d+)-(\\d+)', str(chat))
        if match and owner in {int(match[1]), int(match[2])}:
            return int(match[2]) if int(match[1]) == owner else int(match[1])
        return None

    def tailor(self, text, buyer):
        if not isinstance(text, str) or not buyer or (not self.known(buyer)):
            return text
        pattern = '(?i)(?:остав(?:ьте|ь|ите)\\s+(?:(?:пожалуйста|честный|свой|нам|ваш)\\s+)*отзыв|не забудьте\\s+(?:оставить\\s+)?отзыв|будем рады\\s+(?:вашему\\s+)?(?:честному\\s+)?отзыву|(?:please\\s+)?(?:leave|write|post)\\s+(?:(?:an?|your|honest)\\s+)*review)[^\\n.!?]*(?:[.!?]+|$)'
        prefix = '(?i)(?:остав(?:ьте|ь|ите)\\s+(?:(?:пожалуйста|честный|свой|нам|ваш)\\s+)*отзыв|не забудьте\\s+(?:оставить\\s+)?отзыв|будем рады\\s+(?:вашему\\s+)?(?:честному\\s+)?отзыву|(?:please\\s+)?(?:leave|write|post)\\s+(?:(?:an?|your|honest)\\s+)*review)'
        lines = []
        for line in text.splitlines():
            parts = []
            for sentence in re.split('(?<=[.!?])\\s+', line):
                match = re.search(prefix, sentence)
                kept = sentence[:match.start()].strip() if match else sentence
                if match:
                    kept = re.sub('\\s+(?:и|and)\\s*[,;—–-]?\\s*$', '', kept, flags=re.I).rstrip(' ,;—–-')
                if kept:
                    parts.append(kept)
            cleaned = ' '.join(parts).strip()
            if cleaned:
                lines.append(cleaned)
            elif lines and lines[-1] != '':
                lines.append('')
        return '\n'.join(lines).strip()

    def attach(self, account):
        if getattr(account, '_auto_emoji_review_policy', False):
            return
        original = account.send_message

        @functools.wraps(original)
        def send(*args, **kwargs):
            chat = kwargs.get('chat_id', args[0] if args else None)
            buyer = kwargs.get('interlocutor_id') or self.buyer(chat, getattr(account, 'id', None))
            text = kwargs.get('text', args[1] if len(args) > 1 else None)
            new = self.tailor(text, buyer)
            if isinstance(text, str) and new != text:
                if 'text' in kwargs:
                    kwargs['text'] = new
                elif len(args) > 1:
                    args = (args[0], new, *args[2:])
            if isinstance(new, str) and (not new.strip(' 💙\n')):
                return None
            return original(*args, **kwargs)
        account.send_message = send
        account._auto_emoji_review_policy = True
