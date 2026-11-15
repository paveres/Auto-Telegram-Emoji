import os
os.environ.setdefault('PUBLIC_BASE_URL', 'https://preview.example.test')
import unittest, tempfile, zipfile, hashlib
from pathlib import Path
from auto_telegram_emoji.store import Store
from auto_telegram_emoji.wallet import Wallet
from auto_telegram_emoji.aliases import normalize, YES, NO
from auto_telegram_emoji.archive import Archive

class Tests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.s = Store(self.root / 'orders.sqlite3')
        self.w = Wallet(self.s)

    def test_aliases_context(self):
        for word in YES:
            self.assertEqual(normalize(word, 'confirm'), '+')
        for word in NO:
            self.assertEqual(normalize(word, 'preview'), '-')
        self.assertEqual(normalize('да', 'nick'), 'да')
        self.assertEqual(normalize('Получить список команд'), '!меню')
        self.assertEqual(normalize('градиенты'), '!градиент')
        self.assertEqual(normalize('!ник MyNick', 'preview'), '!текст MyNick')

    def test_wallet_once_reserve_release(self):
        self.assertTrue(self.w.credit(5, 'A'))
        self.assertFalse(self.w.credit(5, 'A'))
        self.w.credit(5, 'B')
        self.assertEqual(self.w.balance(5), 4)
        self.w.reserve(5, 'GIFT', 3)
        self.w.reserve(5, 'GIFT', 3)
        self.assertEqual(self.w.balance(5), 1)
        with self.assertRaises(ValueError):
            self.w.reserve(5, 'OTHER', 2)
        self.w.settle('GIFT', False)
        self.assertEqual(self.w.balance(5), 4)

    def test_wallet_spend_survives_restart(self):
        self.w.credit(5, 'A')
        self.w.reserve(5, 'GIFT', 2)
        self.w.settle('GIFT', True)
        self.w.settle('GIFT', True)
        self.assertEqual(Wallet(Store(self.s.path)).balance(5), 0)

    def test_history_reissues_closed_exact_files(self):
        self.s.add('OLD', 5, '123', 1)
        folder = self.root / 'old'
        folder.mkdir()
        zpath = folder / 'emoji.zip'
        with zipfile.ZipFile(zpath, 'w') as z:
            z.writestr('1.tgs', b'original')
        video = folder / 'preview.mp4'
        video.write_bytes(b'video')
        with self.s.tx() as db:
            db.execute('INSERT INTO links VALUES(?,?,0,?,?)', ('old', 'OLD', str(video), str(zpath)))
        self.s.close('OLD', 'CLOSED')
        service = Archive(self.s)
        self.assertEqual(service.creations(6), [])
        rows = service.creations(5)
        self.assertEqual(len(rows), 1)
        link = service.renew(rows[0], 5, 'request')
        self.assertEqual(link, service.renew(rows[0], 5, 'request'))
        with self.s.tx() as db:
            path = db.execute('SELECT archive FROM links WHERE active=1').fetchone()[0]
        with zipfile.ZipFile(path) as z:
            self.assertEqual(z.read('1.tgs'), b'original')
        with self.assertRaises(ValueError):
            service.renew(rows[0], 6, 'attack')

    def test_public_history_photo_then_information_and_confirmation(self):
        from types import SimpleNamespace as NS
        from auto_telegram_emoji.public import Public
        self.s.add('HISTORY', 5, '123', 1)
        folder = self.root / 'history'
        folder.mkdir()
        archive = folder / 'emoji.zip'
        with zipfile.ZipFile(archive, 'w') as z:
            z.writestr('original.tgs', b'exact original')
        video = folder / 'preview.mp4'
        video.write_bytes(b'video')
        (folder / 'preview-1.jpg').write_bytes(b'photo')
        order = self.s.get('HISTORY')
        order['data'].update(nick='CAPY', artifact_archive=str(archive), artifact_video=str(video))
        self.s.save(order)
        self.s.close('HISTORY', 'CLOSED')
        with self.s.tx() as db:
            db.execute('INSERT INTO links VALUES(?,?,0,?,?)', ('history-link', 'HISTORY', str(video), str(archive)))
        a = NS(store=self.s, transport=NS(flush=lambda o: None))
        public = Public(a)
        self.assertTrue(public.handle(5, '123', '!мои', 'h1'))
        self.assertTrue(public.handle(5, '123', '1', 'h2'))
        with self.s.tx() as db:
            rows = db.execute("SELECT kind,payload FROM outbox WHERE oid='PUBLIC-5' ORDER BY rowid").fetchall()
        self.assertTrue(any((row[0] == 'image' for row in rows)))
        self.assertEqual(self.s.get('PUBLIC-5')['stage'], 'archive_confirm')
        self.assertTrue(public.handle(5, '123', 'да', 'h3'))
        self.assertEqual(self.s.get('PUBLIC-5')['stage'], 'public')
        with self.s.tx() as db:
            linked = db.execute('SELECT archive FROM links WHERE active=1').fetchone()[0]
        with zipfile.ZipFile(linked) as z:
            self.assertEqual(z.read('original.tgs'), b'exact original')
