__author__ = '@justmeth'
__channel__ = 'https://t.me/g_plugins'
__contact__ = 'https://t.me/justmeth'
import hashlib, threading, time, re
from pathlib import Path
from urllib.parse import urlsplit
import requests

class DeliveryPending(RuntimeError):
    pass

def normal_text(value):
    return re.sub('\\s+', ' ', re.sub('[\u2061\u2060\u200b\ufeff]', '', value or '')).strip()

class Transport:

    def __init__(self, runtime, store):
        self.runtime = runtime
        self.store = store
        self.lock = runtime.account.__dict__.setdefault('_auto_emoji_delivery_lock', threading.RLock())
        self.last_checks = {}

    def receipt(self, o, r):
        with self.store.tx() as db:
            floor = db.execute("SELECT MAX(CAST(remote AS INTEGER)) FROM outbox WHERE oid=? AND state='sent' AND rowid<(SELECT rowid FROM outbox WHERE key=?)", (o['id'], r['key'])).fetchone()[0] or 0
        history = self.runtime.account.get_chat_history(o['chat'])
        if r['kind'] == 'text':
            return next((m for m in history if m.author_id == self.runtime.account.id and int(m.id) > floor and (normal_text(m.text) == normal_text(r['payload']))), None)
        expected = hashlib.sha256(Path(r['payload']).read_bytes()).digest()
        for m in history[-12:]:
            url = getattr(m, 'image_link', None)
            if m.author_id != self.runtime.account.id or int(m.id) <= floor or (not url):
                continue
            host = urlsplit(url).hostname or ''
            if urlsplit(url).scheme != 'https' or not (host in {'funpay.com', 'sfunpay.com'} or host.endswith(('.funpay.com', '.sfunpay.com'))):
                continue
            res = requests.get(url, timeout=(5, 10), allow_redirects=False)
            if res.status_code == 200 and hashlib.sha256(res.content).digest() == expected:
                return m
        return None

    @staticmethod
    def blocked(o):
        return not o or o['stage'] in {'REFUNDED', 'CANCELLED'} or o['data'].get('outbound_suppressed')

    def flush(self, o, events_only=False):
        with self.store.tx() as db:
            rows = [dict(r) for r in db.execute("SELECT * FROM outbox WHERE oid=? AND state IN ('pending','sending','uncertain') ORDER BY rowid", (o['id'],))]
        for r in rows:
            event = ':event:' in r['key']
            if events_only and (not event):
                continue
            current = self.store.get(o['id'])
            if self.blocked(current):
                return
            if current['stage'] == 'CLOSED' and (not event):
                continue
            from auto_telegram_emoji.platform import service_enabled
            from . import SERVICE_ID
            if not service_enabled(self.runtime, SERVICE_ID):
                return
            if r['state'] in {'sending', 'uncertain'}:
                if time.monotonic() < self.last_checks.get(r['key'], 0):
                    raise DeliveryPending('Ожидается сверка доставки.')
                self.last_checks[r['key']] = time.monotonic() + 30
                found = self.receipt(o, r)
                if not found:
                    raise DeliveryPending('Неизвестный результат отправки; нужна сверка журнала')
                with self.store.tx() as db:
                    db.execute("UPDATE outbox SET state='sent',remote=? WHERE key=?", (str(found.id), r['key']))
                continue
            with self.store.tx() as db:
                db.execute("UPDATE outbox SET state='sending' WHERE key=?", (r['key'],))
            try:
                with self.lock:
                    time.sleep(max(0, self.runtime.account.__dict__.get('_auto_emoji_next_send', 0) - time.monotonic()))
                    if self.blocked(self.store.get(o['id'])):
                        with self.store.tx() as db:
                            db.execute("UPDATE outbox SET state='suppressed' WHERE key=?", (r['key'],))
                        return
                    chat = int(o['chat']) if o['chat'].isdigit() else o['chat']
                    if r['kind'] == 'image':
                        result = self.runtime.account.send_image(chat, r['payload'], interlocutor_id=o['buyer'])
                    else:
                        result = self.runtime.account.send_message(chat, r['payload'], interlocutor_id=o['buyer'])
                    self.runtime.account.__dict__['_auto_emoji_next_send'] = time.monotonic() + 1.2
                if not result or not result.id:
                    raise RuntimeError('Отправка не подтверждена')
                with self.store.tx() as db:
                    db.execute("UPDATE outbox SET state='sent',remote=? WHERE key=?", (str(result.id), r['key']))
            except Exception as error:
                from FunPayAPI.common.exceptions import MessageNotDeliveredError
                rejected = isinstance(error, MessageNotDeliveredError) and any((x in str(getattr(error, 'error_message', '')).lower() for x in ('слишком часто', 'too frequently', 'надто часто', 'надто швидко')))
                if rejected:
                    self.runtime.account.__dict__['_auto_emoji_next_send'] = time.monotonic() + 5
                if not rejected:
                    try:
                        found = self.receipt(o, r)
                    except Exception:
                        found = None
                    if found:
                        with self.store.tx() as db:
                            db.execute("UPDATE outbox SET state='sent',remote=? WHERE key=?", (str(found.id), r['key']))
                        continue
                    self.last_checks[r['key']] = time.monotonic() + 30
                with self.store.tx() as db:
                    db.execute('UPDATE outbox SET state=? WHERE key=?', ('pending' if rejected else 'uncertain', r['key']))
                raise
        from .input_gate import InputGate
        InputGate(self.store).delivered(o)
