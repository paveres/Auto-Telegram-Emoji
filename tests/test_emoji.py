import os
os.environ.setdefault('PUBLIC_BASE_URL', 'https://preview.example.test')
import tempfile, unittest
from pathlib import Path
from auto_telegram_emoji.parser import numbers
from auto_telegram_emoji.store import Store
from auto_telegram_emoji.engine import Engine

class Cat:
    base = Path('.')

    def collections(self):
        return ['classic', 'love']

    def items(self, c):
        return list(range(50))

    def label(self, c, n):
        return c + ' ' + str(n)

class Render:

    def collections(self):
        return []

    def collection(self, c):
        return []

    def selected(self, o, personal=False):
        return ([], [], Path('.'))

    def build(self, o, final=False):
        if not o['data']['nick'].strip():
            raise ValueError('Введите ник')
        return ([], Path('preview.mp4'), Path('emoji.zip') if final else None)

class Tests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.s = Store(Path(self.tmp.name) / 'orders.db')
        self.s.add('ABC', 42, '123', 5)
        self.e = Engine(self.s, Cat(), Render())
        self.n = 0

    def send(self, text):
        self.n += 1
        o = self.s.get('ABC')
        self.e.handle(o, text, str(self.n))
        if o['stage'] == 'catalog_pending':
            self.e.send_catalog(o)
        return self.s.get('ABC')

    def test_parser(self):
        for text in ['1, 5;47', '№1 №5 №47', '1\n5\n47', '1 и 5 и 47']:
            self.assertEqual(numbers(text), [1, 5, 47])
        self.assertEqual(numbers('1–3,2'), [1, 2, 3])
        for text in ['0', '51', '85', '1.5', 'https://x/1', '1-500000', '5-1', 'abc1']:
            with self.assertRaises(ValueError):
                numbers(text)

    def test_mixed_and_limit(self):
        self.send('1')
        self.send('1,2')
        self.send('!коллекции')
        self.send('2')
        o = self.send('1,2,3,4')
        self.assertEqual(len(o['data']['cart']), 2)
        o = self.send('1,2,3')
        self.assertEqual(o['stage'], 'confirm')
        self.assertEqual(len(o['data']['cart']), 5)
        self.send('+')
        self.assertEqual(self.s.get('ABC')['stage'], 'text_pick')
        self.assertEqual(len(self.s.get('ABC')['data']['cart']), 5)
        self.send('1')
        from unittest.mock import patch
        from types import SimpleNamespace
        with patch.dict('sys.modules', {'auto_telegram_emoji.vector': SimpleNamespace(outlines=lambda *a: None)}):
            o = self.send('123')
        self.assertEqual(o['data']['texts']['1'], '123')
        o = self.send('готово')
        self.assertEqual(o['stage'], 'preview')
        self.send('+')
        self.assertEqual(self.s.get('ABC')['stage'], 'pack_type')
        self.send('2')
        self.assertEqual(self.s.get('ABC')['stage'], 'generating')

    def test_duplicate_input(self):
        o = self.s.get('ABC')
        self.e.handle(o, '1', 'same')
        o = self.s.get('ABC')
        self.e.handle(o, '1', 'same')
        self.assertEqual(self.s.get('ABC')['stage'], 'catalog_pending')
        self.assertEqual(self.s.get('ABC')['data']['cart'], [])

    def test_replacement_cancel(self):
        self.send('1')
        self.send('1,2')
        self.send('!смена')
        self.send('2')
        self.send('3')
        o = self.send('!отмена')
        self.assertEqual(o['data']['cart'], [['classic', 1], ['classic', 2]])

    def test_terminal_cannot_resurrect(self):
        stale = self.s.get('ABC')
        self.s.close('ABC', 'REFUNDED')
        stale['stage'] = 'delivered'
        self.s.save(stale)
        self.assertEqual(self.s.get('ABC')['stage'], 'REFUNDED')

    def test_reopen_database(self):
        self.send('1')
        self.send('1,2')
        other = Store(self.s.path)
        self.assertEqual(len(other.get('ABC')['data']['cart']), 2)

    def test_sign_is_not_nickname(self):
        o = self.s.get('ABC')
        o['stage'] = 'nick'
        self.s.save(o)
        o = self.send('+')
        self.assertEqual(o['stage'], 'nick')
        self.assertEqual(o['data']['nick'], '')
if __name__ == '__main__':
    unittest.main()
