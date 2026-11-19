__author__ = '@paveres'
__channel__ = 'https://t.me/g_plugins'
__contact__ = 'https://t.me/paveres'
from .links import base_url
'Buyer-scoped history of exact stored files, independent of order closure.'
import hashlib, secrets, time, zipfile
from pathlib import Path

class Archive:

    def __init__(self, store):
        self.store = store

    def creations(self, buyer):
        result = []
        with self.store.tx() as db:
            for row in db.execute('SELECT o.*,l.archive,l.video FROM orders o JOIN links l ON l.oid=o.id WHERE o.buyer=? AND l.archive IS NOT NULL ORDER BY o.created DESC', (buyer,)):
                o = self.store.decode(row)
                if o['data'].get('kind') in {'public', 'archive'} or not Path(row['archive']).is_file():
                    continue
                o['archive'] = row['archive']
                o['video'] = row['video']
                result.append(o)
        return result

    def renew(self, creation, buyer, request_key):
        if creation['buyer'] != buyer:
            raise ValueError('Этот набор принадлежит другому покупателю.')
        with zipfile.ZipFile(creation['archive']) as z:
            if z.testzip() or not z.namelist():
                raise ValueError('Архив повреждён. Напишите продавцу.')
            count = len(z.namelist())
        oid = 'ARCHIVE' + hashlib.sha256((str(buyer) + request_key).encode()).hexdigest()[:12].upper()
        old = self.store.get(oid)
        if old and old['data'].get('token'):
            return base_url() + '/' + old['data']['token'] + '/download'
        dest = Path(creation['archive'])
        self.store.add(oid, buyer, creation['chat'], count)
        o = self.store.get(oid)
        token = ''.join((secrets.choice('abcdefghijklmnopqrstuvwxyz0123456789') for _ in range(8)))
        with self.store.tx() as db:
            while db.execute('SELECT 1 FROM links WHERE token=?', (hashlib.sha256(token.encode()).hexdigest(),)).fetchone():
                token = ''.join((secrets.choice('abcdefghijklmnopqrstuvwxyz0123456789') for _ in range(8)))
            db.execute('INSERT INTO links VALUES(?,?,1,?,?)', (hashlib.sha256(token.encode()).hexdigest(), oid, creation['video'], str(dest)))
        o['stage'] = 'delivered'
        o['data'].update(kind='archive', source_order=creation['id'], token=token, access_until=time.time() + 7 * 86400)
        self.store.save(o)
        return base_url() + '/' + token + '/download'
