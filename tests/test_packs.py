import os
os.environ.setdefault('PUBLIC_BASE_URL', 'https://preview.example.test')
import gzip, json, tempfile, unittest, zipfile
from pathlib import Path
from auto_telegram_emoji.store import Store
from auto_telegram_emoji.packs import Packs, PackPending, PackError, Telegram
from types import SimpleNamespace
from auto_telegram_emoji.engine import Engine
from auto_telegram_emoji.aliases import normalize
from auto_telegram_emoji.pack_admin import Admin

class API:

    def __init__(self):
        self.sets = {}
        self.calls = []
        self.interrupt = None
        self.seq = 0

    def call(self, method, data=None, files=None, missing=False):
        self.calls.append(method)
        data = data or {}
        if method == 'getStickerSet':
            return self.sets.get(data['name'])
        if method == 'uploadStickerFile':
            self.seq += 1
            return {'file_id': str(self.seq)}
        if method == 'createNewStickerSet':
            self.sets[data['name']] = {'sticker_type': data['sticker_type'], 'stickers': json.loads(data['stickers'])}
        elif method == 'addStickerToSet':
            self.sets[data['name']]['stickers'].append(json.loads(data['sticker']))
        else:
            raise AssertionError(method)
        if self.interrupt == method:
            self.interrupt = None
            raise PackPending(9)
        return True

class Tests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.s = Store(self.root / 'orders.db')
        self.api = API()

    def order(self, count=3, kind='custom_emoji', oid='TEST'):
        self.s.add(oid, 7, '8', count)
        o = self.s.get(oid)
        o['data'].update(pack_kind=kind, nick='DEMO')
        return o

    def archive(self, count=3, bad=False):
        p = self.root / 'test.zip'
        with zipfile.ZipFile(p, 'w') as z:
            for i in range(count):
                z.writestr(str(i) + '.tgs', gzip.compress(json.dumps({'w': 512, 'h': 512, 'fr': 60, 'op': 240 if bad else 60, 'layers': [], 'test': i}).encode()))
        return p

    def publisher(self):
        return Packs(self.root, self.s, self.api, 99, 'ExampleBot')

    def test_both_types_and_idempotence(self):
        for i, kind in enumerate(['regular', 'custom_emoji']):
            o = self.order(kind=kind, oid=str(i))
            p = self.archive()
            urls = self.publisher().publish(o, p)
            self.assertIn('addstickers/' if kind == 'regular' else 'addemoji/', urls[0])
            calls = len(self.api.calls)
            self.assertEqual(self.publisher().publish(o, p), urls)
            self.assertEqual(len(self.api.calls), calls + 1)
        self.assertEqual([r['number'] for r in self.publisher().rows('1')], [2])

    def test_unknown_creation_resumes_without_duplicate(self):
        self.api.interrupt = 'createNewStickerSet'
        o = self.order()
        p = self.archive()
        with self.assertRaises(PackPending):
            self.publisher().publish(o, p)
        self.publisher().publish(o, p)
        self.assertEqual(self.api.calls.count('createNewStickerSet'), 1)
        self.assertEqual(len(next(iter(self.api.sets.values()))['stickers']), 3)

    def test_unknown_add_resumes_without_duplicate(self):
        self.api.interrupt = 'addStickerToSet'
        o = self.order()
        p = self.archive()
        with self.assertRaises(PackPending):
            self.publisher().publish(o, p)
        self.publisher().publish(o, p)
        self.assertEqual(self.api.calls.count('addStickerToSet'), 2)

    def test_large_sticker_order_splits(self):
        urls = self.publisher().publish(self.order(200, 'regular'), self.archive(200))
        self.assertEqual(len(urls), 2)
        self.assertEqual([len(v['stickers']) for v in self.api.sets.values()], [120, 80])

    def test_invalid_animation_never_creates_pack(self):
        with self.assertRaises(PackError):
            self.publisher().publish(self.order(), self.archive(bad=True))
        self.assertFalse(self.api.calls)

    def test_selection_and_return(self):
        o = self.order()
        o['stage'] = 'preview'
        e = Engine(self.s, None, None)
        e.handle(o, 'да', '1')
        self.assertEqual(o['stage'], 'pack_type')
        e.handle(o, '8', '2')
        self.assertEqual(o['stage'], 'pack_type')
        e.handle(o, '!продолжить', '3')
        self.assertEqual(o['stage'], 'pack_type')
        e.preview = lambda order: order.update(stage='preview')
        e.handle(o, '!назад', '4')
        self.assertEqual(o['stage'], 'preview')
        e.handle(o, 'да', '5')
        e.handle(o, '2', '6')
        self.assertEqual(o['stage'], 'generating')
        self.assertEqual(o['data']['pack_kind'], 'custom_emoji')
        self.assertEqual(normalize('пак'), '!пак')

    def test_telegram_retry_and_secret_redaction(self):
        api = Telegram('secret-token')
        api.session = SimpleNamespace(post=lambda *a, **kw: SimpleNamespace(status_code=429, json=lambda: {'ok': False, 'error_code': 429, 'parameters': {'retry_after': 123}}))
        with self.assertRaises(PackPending) as cm:
            api.call('uploadStickerFile')
        self.assertEqual(cm.exception.delay, 123)
        api.session = SimpleNamespace(post=lambda *a, **kw: SimpleNamespace(status_code=400, json=lambda: {'ok': False, 'error_code': 400, 'description': 'secret-token'}))
        with self.assertRaises(PackError) as cm:
            api.call('createNewStickerSet')
        self.assertNotIn('secret-token', str(cm.exception))

    def test_admin_only_owner_private_chat(self):
        calls = []
        api = SimpleNamespace(call=lambda *args, **kw: calls.append((args, kw)))
        a = Admin(self.root, api, 99)
        for sender, chat, kind in [(98, 98, 'private'), (99, -1, 'group'), (98, 99, 'private')]:
            self.assertFalse(a.handle({'message': {'from': {'id': sender}, 'chat': {'id': chat, 'type': kind}, 'text': '/start'}}))
            self.assertFalse(a.handle({'callback_query': {'id': 'q', 'from': {'id': sender}, 'data': 'admin:home', 'message': {'chat': {'id': chat, 'type': kind}, 'message_id': 1}}}))
        self.assertFalse(calls)
        self.assertTrue(a.handle({'message': {'from': {'id': 99}, 'chat': {'id': 99, 'type': 'private'}, 'text': '/start'}}))
        markup = json.loads(calls[0][0][1]['reply_markup'])
        self.assertEqual(markup['inline_keyboard'][0][0]['text'], 'Созданные паки')

    def test_invalid_chat_is_silent_and_limit_is_clear(self):
        o = self.order(5)
        o['stage'] = 'collection'
        e = Engine(self.s, SimpleNamespace(collections=lambda: ['classic'], items=lambda c: list(range(30))), None)
        for i, text in enumerate(['мусор', '100', '!несуществующая']):
            e.handle(o, text, str(i))
        with self.s.tx() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM outbox').fetchone()[0], 0)
        o['stage'] = 'select'
        o['data']['collection'] = 'classic'
        e.handle(o, '8,7,12,24,18,1', 'limit')
        with self.s.tx() as db:
            self.assertEqual(db.execute('SELECT payload FROM outbox').fetchone()[0], 'Превышен лимит выбора.\n\nДоступно: 5 эмодзи\nБонусных: 0')
        self.assertEqual(o['data']['cart'], [])

    def test_each_emoji_has_independent_text_and_skip(self):
        from auto_telegram_emoji.textflow import open_menu, value
        from unittest.mock import patch
        o = self.order(3)
        o['data']['cart'] = [['classic', 1], ['love', 2], ['classic', 3]]
        render = SimpleNamespace(selected=lambda *a: ([], [], None), build=lambda *a: ([], Path('video'), None))
        e = Engine(self.s, SimpleNamespace(base=self.root), render)
        open_menu(e, o)
        with patch.dict('sys.modules', {'auto_telegram_emoji.vector': SimpleNamespace(outlines=lambda *a: None)}):
            for position, text in [(1, 'ONE'), (2, 'TWO'), (3, 'THREE')]:
                e.handle(o, str(position), 'pick' + str(position))
                e.handle(o, text, 'text' + str(position))
            e.handle(o, '2', 'pick-again')
            e.handle(o, '-', 'keep')
        self.assertEqual([value(o['data'], i) for i in [1, 2, 3]], ['ONE', 'TWO', 'THREE'])
        e.handle(o, 'готово', 'done')
        self.assertEqual(o['stage'], 'preview')

    def test_start_reminder_precedes_any_images(self):
        o = self.order()
        render = SimpleNamespace(collections=lambda: (_ for _ in ()).throw(AssertionError('rendered before notice')))
        cat = SimpleNamespace(collections=lambda: ['classic'])
        e = Engine(self.s, cat, render)
        e.start(o)
        self.assertEqual(self.s.get(o['id'])['stage'], 'intro_pending')
        render.collections = lambda: ['image.png']
        e.collections(o)
        with self.s.tx() as db:
            rows = db.execute('SELECT kind,payload FROM outbox ORDER BY rowid').fetchall()
        reminder = next((i for i, r in enumerate(rows) if r['payload'].startswith('Напоминание:')))
        photo = next((i for i, r in enumerate(rows) if r['kind'] == 'image'))
        self.assertLess(reminder, photo)

    def test_collection_notice_is_saved_before_render(self):
        o = self.order()
        render = SimpleNamespace(collection=lambda c: (_ for _ in ()).throw(AssertionError('rendered before notice')))
        e = Engine(self.s, SimpleNamespace(collections=lambda: ['classic'], items=lambda c: [1, 2]), render)
        e.handle(o, '1', 'choice')
        self.assertEqual(self.s.get(o['id'])['stage'], 'catalog_pending')
        with self.s.tx() as db:
            self.assertEqual(db.execute('SELECT payload FROM outbox').fetchone()[0], 'Отправляю варианты. Дождитесь всех фотографий.')
        e.handle(o, '2', 'spam')
        self.assertEqual(o['data']['collection'], 'classic')
        render.collection = lambda c: []
        e.send_catalog(o)
        self.assertEqual(self.s.get(o['id'])['stage'], 'select')

    def test_command_list_before_and_after_purchase(self):
        from auto_telegram_emoji.public import Public
        a = SimpleNamespace(store=self.s, engine=Engine(self.s, None, None), transport=SimpleNamespace(flush=lambda *args: None))
        public = Public(a)
        for i, (text, active) in enumerate([('!команды', None), ('Получить команды', {'stage': 'collection', 'data': {'started': True}}), ('!команды', {'stage': 'CLOSED', 'data': {}})]):
            self.assertEqual(normalize(text), '!меню')
            self.assertTrue(public.handle(10 + i, 'chat', text, 'key' + str(i), active))
        for line in a.engine.help().splitlines():
            if line.startswith('!'):
                self.assertIn(' - ', line)
                self.assertNotIn(' · ', line)
if __name__ == '__main__':
    unittest.main()
