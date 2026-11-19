__author__ = '@paveres'
__channel__ = 'https://t.me/g_plugins'
__contact__ = 'https://t.me/paveres'
import os
from urllib.parse import urlsplit

def base_url():
    url = os.environ.get('PUBLIC_BASE_URL', '').strip().rstrip('/')
    parsed = urlsplit(url)
    if parsed.scheme not in {'https', 'http'} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or (parsed.path not in {'', '/'}) or any((c.isspace() for c in url)):
        raise ValueError('Укажите PUBLIC_BASE_URL без дополнительного пути')
    return url
