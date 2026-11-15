__author__ = '@justmeth'
__channel__ = 'https://t.me/g_plugins'
__contact__ = 'https://t.me/justmeth'
import hashlib, hmac, html, re, secrets, sqlite3, time, threading, json
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from http.cookies import SimpleCookie
from urllib.parse import urlsplit
from contextlib import closing
from .links import base_url
ROOT = Path.cwd()
FOLDER = ROOT / 'data'
LIMITS = {}
LOCK = threading.Lock()

def lookup(digest):
    with closing(sqlite3.connect(FOLDER / 'orders.sqlite3')) as db:
        row = db.execute("SELECT l.video,l.archive,o.stage,o.data FROM links l JOIN orders o ON o.id=l.oid WHERE l.token=? AND l.active=1 AND o.stage NOT IN ('CLOSED','REFUNDED','CANCELLED')", (digest,)).fetchone()
        if row and min(json.loads(row[3]).get('bonus_expires', time.time() + 1), json.loads(row[3]).get('access_until', time.time() + 1)) < time.time():
            return None
        return row

class Handler(BaseHTTPRequestHandler):

    def log_message(self, *args):
        pass

    def reply(self, status, body=b'', kind='text/plain; charset=utf-8', headers=None):
        self.send_response(status)
        for k, v in {'Content-Type': kind, 'Content-Length': str(len(body)), 'Cache-Control': 'private, no-store', 'Referrer-Policy': 'no-referrer', 'X-Content-Type-Options': 'nosniff', 'X-Frame-Options': 'DENY', 'X-Robots-Tag': 'noindex, nofollow, noarchive', 'Content-Security-Policy': "default-src 'none'; style-src 'unsafe-inline'; media-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'", **(headers or {})}.items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(body)

    def do_GET(self):
        ip = self.headers.get('X-Forwarded-For', self.client_address[0]).split(',')[0].strip()
        minute = int(time.time() / 60)
        with LOCK:
            if len(LIMITS) > 2000:
                for key in list(LIMITS):
                    if LIMITS[key][0] != minute:
                        LIMITS.pop(key, None)
            old, count = LIMITS.get(ip, (minute, 0))
            count = count + 1 if old == minute else 1
            LIMITS[ip] = (minute, count)
        if count > 180:
            return self.reply(429, headers={'Retry-After': '60'})
        path = urlsplit(self.path).path
        if path == '/robots.txt':
            return self.reply(200, b'User-agent: *\nDisallow: /')
        if path == '/media':
            try:
                c = SimpleCookie()
                c.load(self.headers.get('Cookie', ''))
                body, sig = c['ep'].value.rsplit('.', 1)
                digest, expiry = body.split('.')
                if int(expiry) < time.time() or not hmac.compare_digest(sig, hmac.new(KEY, body.encode(), hashlib.sha256).hexdigest()):
                    raise ValueError()
                row = lookup(digest)
                if not row:
                    raise ValueError()
            except Exception:
                return self.reply(404)
            return self.file(row[0], 'video/mp4')
        match = re.fullmatch('/([a-z0-9]{8})(/download)?', path)
        if not match:
            return self.reply(404)
        digest = hashlib.sha256(match[1].encode()).hexdigest()
        row = lookup(digest)
        if not row:
            return self.reply(404)
        if match[2]:
            if row[2] != 'delivered' or not row[1]:
                return self.reply(404)
            return self.file(row[1], 'application/zip', {'Content-Disposition': 'attachment; filename="emoji.zip"'})
        body = digest + '.' + str(int(time.time()) + 3600)
        cookie = body + '.' + hmac.new(KEY, body.encode(), hashlib.sha256).hexdigest()
        page = '<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Предпросмотр</title><style>html,body{margin:0;min-height:100%;background:#000}body{min-height:100svh;display:grid;place-items:center}video{display:block;width:min(100%,1100px);height:auto;max-height:100svh;object-fit:contain}</style><video autoplay muted loop playsinline disablepictureinpicture disableremoteplayback controlslist="nodownload noremoteplayback" aria-label="Выбранные эмодзи"><source src="/media" type="video/mp4"></video></html>'
        secure = 'Secure; ' if base_url().startswith('https:') else ''
        self.reply(200, page.encode(), 'text/html; charset=utf-8', {'Set-Cookie': f'ep={cookie}; HttpOnly; {secure}SameSite=Strict; Path=/; Max-Age=3600'})

    def file(self, name, kind, headers=None):
        p = Path(name).resolve()
        if FOLDER.resolve() not in p.parents or not p.is_file():
            return self.reply(404)
        size = p.stat().st_size
        start = 0
        end = size - 1
        extra = {'Accept-Ranges': 'bytes', **(headers or {})}
        r = self.headers.get('Range', '')
        status = 200
        if r:
            match = re.fullmatch('bytes=(\\d+)-(\\d*)', r)
            if not match:
                return self.reply(416)
            start = int(match[1])
            end = min(size - 1, int(match[2]) if match[2] else size - 1)
            if start > end:
                return self.reply(416)
            status = 206
            extra['Content-Range'] = f'bytes {start}-{end}/{size}'
        remaining = max(0, end - start + 1)
        extra['Content-Length'] = str(remaining)
        self.reply(status, kind=kind, headers=extra)
        if self.command == 'HEAD':
            return
        try:
            with p.open('rb') as stream:
                stream.seek(start)
                while remaining:
                    chunk = stream.read(min(128 * 1024, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass
    do_HEAD = do_GET

def serve(root, host='127.0.0.1', port=8206):
    global ROOT, FOLDER, KEY
    ROOT = Path(root)
    FOLDER = ROOT / 'data'
    FOLDER.mkdir(parents=True, exist_ok=True)
    p = FOLDER / 'web.key'
    if not p.exists():
        p.write_bytes(secrets.token_bytes(32))
        p.chmod(384)
    KEY = p.read_bytes()
    server = ThreadingHTTPServer((host, port), Handler)
    threading.Thread(target=server.serve_forever, name='preview-http', daemon=True).start()
    return server
