import tempfile, unittest, hashlib, os, json
from pathlib import Path
from types import SimpleNamespace as NS
from auto_telegram_emoji.adapter import Adapter
from auto_telegram_emoji.store import Store
from auto_telegram_emoji.bindings import validate, match_order
from auto_telegram_emoji.locking import InstanceLock

class Tests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.store = Store(self.root / 'orders.db')
        self.config = {'enabled': True, 'lots': {'!gemoji_2': {'marker': '!gemoji_2', 'pack_size': 2, 'seller_price_rub': '3.00'}}}
        self.order = NS(id='TEST', status=NS(name='PAID'), seller_id=7, buyer_id=9, currency=NS(name='RUB'), subcategory=NS(id=1), amount=2, sum=6, short_description='Любое название', full_description='Произвольное описание\n!gemoji_2', chat_id='123')
        self.adapter = Adapter.__new__(Adapter)
        self.adapter.store = self.store
        self.adapter.config = lambda: self.config
        self.adapter.k = NS(account=NS(id=7, get_order=lambda oid: self.order))
        self.adapter.alert = lambda *a: None

    def test_marker_last_line_and_arbitrary_title(self):
        self.adapter.accept('TEST')
        self.assertEqual(self.store.get('TEST')['qty'], 4)

    def test_marker_elsewhere_is_not_enough(self):
        for text in ['!gemoji_2\nещё текст', 'описание !gemoji_2', '!gemoji_2\n!gemoji_2']:
            self.order.full_description = text
            self.assertEqual(match_order(self.order, self.config), [])

    def test_foreign_seller_unpaid_and_underpaid_are_ignored(self):
        self.order.seller_id = 8
        self.adapter.accept('TEST')
        self.assertIsNone(self.store.get('TEST'))
        self.order.seller_id = 7
        self.order.status.name = 'CLOSED'
        self.adapter.accept('TEST')
        self.assertIsNone(self.store.get('TEST'))
        self.order.status.name = 'PAID'
        self.order.sum = 5.99
        self.adapter.accept('TEST')
        self.assertIsNone(self.store.get('TEST'))

    def test_repeat_event_does_not_duplicate(self):
        self.adapter.accept('TEST')
        self.adapter.accept('TEST')
        self.assertEqual(len(self.store.all()), 1)

    def test_bad_marker_duplicate_price_and_size_rejected(self):
        for patch in [{'marker': '!x\n!y'}, {'pack_size': 201}, {'seller_price_rub': 'NaN'}, {'seller_price_rub': '0'}]:
            base = self.config['lots']['!gemoji_2']
            old = base.copy()
            base.update(patch)
            with self.assertRaises(ValueError):
                validate(self.config)
            base.clear()
            base.update(old)

    def test_single_instance_lock(self):
        with InstanceLock(self.root / 'app.lock'):
            with self.assertRaises(ValueError):
                with InstanceLock(self.root / 'app.lock'):
                    pass
        with InstanceLock(self.root / 'app.lock'):
            pass
if __name__ == '__main__':
    unittest.main()
