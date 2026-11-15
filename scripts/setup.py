__author__ = '@justmeth'
__channel__ = 'https://t.me/g_plugins'
__contact__ = 'https://t.me/justmeth'
import getpass, json, re, sys
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urlsplit

def ask(label, default=''):
    value = input(label + (' [' + default + ']' if default else '') + ': ').strip()
    return value or default

def main():
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    print('Auto Telegram Emoji — настройка')
    from auto_telegram_emoji.bindings import validate
    env = root / '.env'
    config_path = root / 'config/app.json'
    if env.exists() or config_path.exists():
        if ask('Настройки уже есть. Заменить? да/нет', 'нет').casefold() != 'да':
            return 0
    golden = getpass.getpass('golden_key FunPay: ').strip()
    token = getpass.getpass('Токен Telegram-бота: ').strip()
    owner = ask('Ваш числовой Telegram ID')
    url = ask('Публичный HTTPS-адрес предпросмотра').rstrip('/')
    if not re.fullmatch('[0-9a-fA-F]{32}', golden):
        raise ValueError('golden_key должен содержать 32 символа')
    if not re.fullmatch('\\d+:[A-Za-z0-9_-]{30,}', token) or not owner.isdigit() or int(owner) <= 0:
        raise ValueError('Проверьте токен и Telegram ID')
    parsed = urlsplit(url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or (parsed.path not in {'', '/'}) or any((c.isspace() for c in url)):
        raise ValueError('Нужен HTTPS-адрес без пути, логина и пароля')
    lots = {}
    while True:
        marker = ask('Метка лота, например !gemoji_15. Enter — закончить')
        if not marker:
            break
        size = ask('Количество эмодзи в одном наборе')
        price = ask('Цена продавца за набор, без комиссии покупателя').replace(',', '.')
        try:
            lots[marker] = {'marker': marker, 'pack_size': int(size), 'seller_price_rub': str(Decimal(price))}
            validate({'lots': lots})
        except (ValueError, InvalidOperation):
            lots.pop(marker, None)
            print('Некорректный тариф. Попробуйте ещё раз.')
            continue
    if not lots:
        raise ValueError('Добавьте хотя бы один тариф')
    config = {'enabled': True, 'max_active': 10, 'lots': lots}
    template = ask('Папка с вашими коллекциями TGS. Enter — использовать встроенные коллекции')
    if template:
        from auto_telegram_emoji.import_assets import import_assets
        destination = root / 'data/assets'
        print('Импортировано шаблонов:', import_assets(template, destination))
        import shutil
        shutil.copytree(root / 'assets/fonts', destination / 'fonts', dirs_exist_ok=True)
    from auto_telegram_emoji.catalog import Catalog
    catalog = Catalog(root)
    available = sum((len(catalog.items(c)) for c in catalog.collections()))
    if max((lot['pack_size'] for lot in lots.values())) > available:
        raise ValueError('Для тарифов недостаточно шаблонов. Добавьте коллекции или уменьшите размер набора.')
    config_path.parent.mkdir(exist_ok=True)
    if env.exists():
        env.replace(env.with_suffix('.env.backup'))
    env.write_text('FUNPAY_GOLDEN_KEY=' + golden + '\nTELEGRAM_BOT_TOKEN=' + token + '\nTELEGRAM_OWNER_ID=' + owner + '\nPUBLIC_BASE_URL=' + url + '\nPREVIEW_HOST=127.0.0.1\nPREVIEW_PORT=8206\n', encoding='utf8')
    env.chmod(384)
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding='utf8')
    print('Готово. Добавьте метки последними строками описаний лотов.')
    print('Откройте своего Telegram-бота и нажмите «Запустить». Затем запускайте start.bat или python -m auto_telegram_emoji.')
    return 0
if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, OSError) as error:
        print('Ошибка:', str(error))
        raise SystemExit(1)
