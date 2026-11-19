__author__ = '@paveres'
__channel__ = 'https://t.me/g_plugins'
__contact__ = 'https://t.me/paveres'
import json, time, shutil
from pathlib import Path

class Artifacts:

    def __init__(self, store):
        self.store = store
        self.folder = store.path.parent

    def collect(self):
        root = (self.folder / 'orders').resolve()
        protected = set()
        with self.store.tx() as db:
            for row in db.execute('SELECT video,archive FROM links'):
                for name in row:
                    if name:
                        protected.add(Path(name).resolve().parent)
            for row in db.execute("SELECT payload FROM outbox WHERE kind='image' AND state!='sent'"):
                protected.add(Path(row[0]).resolve().parent)
            for row in db.execute('SELECT data FROM orders'):
                d = json.loads(row[0])
                name = d.get('artifact_archive')
                if name:
                    protected.add(Path(name).resolve().parent)
        removed = 0
        if root.is_dir():
            for order in root.iterdir():
                if not order.is_dir() or order.is_symlink():
                    continue
                revisions = sorted([p for p in order.iterdir() if p.is_dir() and (not p.is_symlink())], key=lambda p: p.stat().st_mtime, reverse=True)
                for path in revisions[5:]:
                    resolved = path.resolve()
                    if root not in resolved.parents or resolved in protected or time.time() - path.stat().st_mtime < 3600:
                        continue
                    shutil.rmtree(resolved)
                    removed += 1
        jobs = self.folder / 'jobs'
        if jobs.is_dir():
            for path in jobs.iterdir():
                if path.is_file() and (not path.is_symlink()) and (time.time() - path.stat().st_mtime > 86400):
                    path.unlink()
        return removed
