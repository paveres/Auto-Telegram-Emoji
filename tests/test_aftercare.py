import os
os.environ.setdefault('PUBLIC_BASE_URL', 'https://preview.example.test')
import unittest, tempfile, time
from pathlib import Path
from types import SimpleNamespace as NS
from auto_telegram_emoji.store import Store
from auto_telegram_emoji.engine import Engine
from auto_telegram_emoji.aftercare import Aftercare
from test_emoji import Cat, Render

class Tests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.s = Store(Path(self.tmp.name) / 'orders.db')
        self.s.add('REALTEST', 42, '123', 5)
        self.e = Engine(self.s, Cat(), Render())
        self.a = Aftercare(self.s, self.e)

    def remote(self, status='PAID', stars=None):
        return NS(buyer_id=42, status=NS(name=status), review=NS(stars=stars) if stars else None)

    def messages(self, oid='REALTEST'):
        with self.s.tx() as db:
            return [r[0] for r in db.execute("SELECT payload FROM outbox WHERE oid=? AND kind='text'", (oid,))]

    def test_bonus_interrupts_nickname_once(self):
        o = self.s.get('REALTEST')
        o['stage'] = 'nick'
        o['data']['cart'] = [['classic', i] for i in range(1, 6)]
        self.s.save(o)
        self.a.observe(self.s.get(o['id']), self.remote(stars=1), now=100)
        o = self.s.get(o['id'])
        self.assertEqual(o['stage'], 'nick')
        self.assertEqual(o['qty'], 5)
        self.assertEqual(self.e.wallet.balance(42), 2)
        o['data']['templates_confirmed'] = True
        self.s.save(o)
        self.e.handle(self.s.get(o['id']), '!бонус использовать 2', 'use')
        self.e.handle(self.s.get(o['id']), 'дап', 'yes')
        o = self.s.get(o['id'])
        self.assertEqual(o['qty'], 7)
        self.assertEqual(len(o['data']['locked_cart']), 5)
        self.a.observe(o, self.remote(stars=5), now=200)
        self.assertEqual(self.s.get(o['id'])['qty'], 7)
        self.e.handle(self.s.get(o['id']), '!убрать 1', 'x')
        self.assertEqual(len(self.s.get(o['id'])['data']['cart']), 5)
        self.e.handle(self.s.get(o['id']), '2', 'y')
        self.e.send_catalog(self.s.get(o['id']))
        self.e.handle(self.s.get(o['id']), '1,2', 'z')
        o = self.s.get(o['id'])
        self.assertEqual(len(o['data']['cart']), 7)
        self.assertEqual(o['stage'], 'confirm')
        self.e.handle(o, '+', 'final')
        self.assertEqual(self.s.get(o['id'])['stage'], 'text_pick')

    def test_nickname_and_style_survive_bonus(self):
        o = self.s.get('REALTEST')
        o['stage'] = 'preview'
        o['data'].update(cart=[['classic', i] for i in range(1, 6)], nick='CAPY', gradient=2, color=3)
        self.s.save(o)
        self.a.observe(o, self.remote(stars=2), now=100)
        o = self.s.get(o['id'])
        self.assertEqual(o['data']['nick'], 'CAPY')
        self.assertEqual(o['data']['gradient'], 2)
        self.assertEqual(o['data']['color'], 3)

    def test_daily_reminder_and_review_suppression(self):
        o = self.s.get('REALTEST')
        o['stage'] = 'delivered'
        o['data'].update(completion_version=11, delivered_at=0, last_confirmation_contact=0)
        self.s.save(o)
        self.a.observe(o, self.remote(), now=86399)
        self.assertEqual(self.messages(), [])
        self.a.observe(self.s.get(o['id']), self.remote(), now=86400)
        count = len(self.messages())
        self.assertGreater(count, 0)
        self.assertTrue(any(('отзыв' in x for x in self.messages())))
        self.a.observe(self.s.get(o['id']), self.remote(), now=86401)
        self.assertEqual(len(self.messages()), count)
        self.a.observe(self.s.get(o['id']), self.remote(stars=1), now=172800)
        new = self.messages()[count:]
        self.assertFalse(any(('оставьте' in x.lower() for x in new)))
        self.a.observe(self.s.get(o['id']), self.remote('CLOSED', 1), now=200000)
        closedcount = len(self.messages())
        self.a.observe(self.s.get(o['id']), self.remote('CLOSED', 1), now=400000)
        self.assertEqual(len(self.messages()), closedcount)

    def test_late_review_creates_one_independent_bonus(self):
        o = self.s.get('REALTEST')
        o['stage'] = 'delivered'
        o['data']['nick'] = 'NICK'
        self.s.save(o)
        self.a.observe(o, self.remote(stars=3), now=100)
        self.a.observe(self.s.get(o['id']), self.remote(stars=5), now=200)
        self.assertIsNone(self.s.get('REALTEST-BONUS'))
        self.assertEqual(self.e.wallet.balance(42), 2)
        self.assertEqual(self.s.get('REALTEST')['qty'], 5)
        self.assertEqual(len(self.s.all()), 1)

    def test_confirmed_never_asks_for_review(self):
        o = self.s.get('REALTEST')
        o['stage'] = 'delivered'
        self.s.save(o)
        self.a.observe(o, self.remote('CLOSED'), now=100)
        self.assertTrue(self.messages())
        self.assertFalse(any(('отзыв' in x.lower() for x in self.messages())))
        self.assertEqual(self.s.get('REALTEST')['stage'], 'CLOSED')

    def test_closed_with_review_before_delivery_gets_child(self):
        o = self.s.get('REALTEST')
        o['stage'] = 'nick'
        self.s.save(o)
        self.a.observe(o, self.remote('CLOSED', 1), now=100)
        self.assertEqual(self.e.wallet.balance(42), 2)
        self.assertEqual(self.s.get('REALTEST')['stage'], 'CLOSED')

    def test_refund_never_awards_bonus(self):
        self.a.observe(self.s.get('REALTEST'), self.remote('REFUNDED', 5))
        self.assertIsNone(self.s.get('REALTEST-BONUS'))
        self.assertEqual(self.s.get('REALTEST')['stage'], 'REFUNDED')
