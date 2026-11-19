__author__ = '@paveres'
__channel__ = 'https://t.me/g_plugins'
__contact__ = 'https://t.me/paveres'
import json, os, re
from pathlib import Path
from dotenv import load_dotenv
from .bindings import validate

def credentials(root):
    load_dotenv(Path(root) / '.env', override=False)
    return {'token': os.environ.get('TELEGRAM_BOT_TOKEN', ''), 'owner_id': int(os.environ.get('TELEGRAM_OWNER_ID', '0'))}

def load(root):
    root = Path(root)
    creds = credentials(root)
    golden = os.environ.get('FUNPAY_GOLDEN_KEY', '')
    if not re.fullmatch('[0-9a-fA-F]{32}', golden):
        raise ValueError('Заполните FUNPAY_GOLDEN_KEY в .env')
    if not re.fullmatch('\\d+:[A-Za-z0-9_-]{30,}', creds['token']) or creds['owner_id'] <= 0:
        raise ValueError('Заполните токен бота и Telegram ID в .env')
    config = validate(json.loads((root / 'config/app.json').read_text(encoding='utf8')))
    from .links import base_url
    base_url()
    return (config, golden, creds)
