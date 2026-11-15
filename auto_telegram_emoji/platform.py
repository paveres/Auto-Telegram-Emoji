__author__ = '@justmeth'
__channel__ = 'https://t.me/g_plugins'
__contact__ = 'https://t.me/justmeth'
import html
from types import SimpleNamespace
from . import SERVICE_ID
from .packs import Telegram

def service_enabled(context, service=None):
    return context.enabled

def selected(root, buyer, service=None):
    return SERVICE_ID

def escape_html(text):
    return html.escape(str(text))

def emoji(name):
    return '<tg-emoji emoji-id="6028435952299413210">ℹ</tg-emoji>'

class Notifications:

    def __init__(self, token, owner):
        self.api = Telegram(token)
        self.authorized_users = [owner]
        self.bot = self

    def send_message(self, user, text, **kwargs):
        if user not in self.authorized_users:
            raise ValueError('No access')
        result = self.api.call('sendMessage', {'chat_id': user, 'text': text, **kwargs})
        return SimpleNamespace(message_id=result['message_id'])
