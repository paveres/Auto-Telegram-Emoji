__author__ = '@justmeth'
__channel__ = 'https://t.me/g_plugins'
__contact__ = 'https://t.me/justmeth'
import argparse, json, logging, os, signal, threading, time
from pathlib import Path
from types import SimpleNamespace
from FunPayAPI import Account, Runner
from .adapter import Adapter
from .platform import Notifications
from .settings import load
from .pack_admin import Admin
from .locking import InstanceLock

def main():
    parser = argparse.ArgumentParser(prog='Auto Telegram Emoji')
    parser.add_argument('--root', type=Path, default=Path.cwd())
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    root = args.root.resolve()
    os.chdir(root)
    os.environ['AUTO_EMOJI_ROOT'] = str(root)
    try:
        config, golden, creds = load(root)
        from .catalog import Catalog
        catalog = Catalog(root)
        if not catalog.collections():
            raise ValueError('Нет шаблонов: запустите мастер настройки')
        if not config.get('lots'):
            raise ValueError('Добавьте тарифы через мастер настройки')
        available = sum((len(catalog.items(c)) for c in catalog.collections()))
        if max((v['pack_size'] for v in config['lots'].values())) > available:
            raise ValueError('Для тарифов недостаточно шаблонов')
        if args.check:
            print('Настройки корректны. Коллекций:', len(catalog.collections()), 'Тарифов:', len(config['lots']))
            return 0
        with InstanceLock(root / 'data/run.lock'):
            logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
            account = Account(golden).get()
            context = SimpleNamespace(account=account, enabled=True, telegram=Notifications(creds['token'], creds['owner_id']))
            adapter = Adapter(context, root)
            from .web import serve
            server = serve(root, os.environ.get('PREVIEW_HOST', '127.0.0.1'), int(os.environ.get('PREVIEW_PORT', '8206')))
            stopping = threading.Event()

            def stop(*args):
                stopping.set()
                adapter.stop.set()
            signal.signal(signal.SIGINT, stop)
            if hasattr(signal, 'SIGTERM'):
                signal.signal(signal.SIGTERM, stop)

            def events():
                while not stopping.is_set():
                    try:
                        for event in Runner(account).listen(requests_delay=4, ignore_exceptions=False):
                            if stopping.is_set():
                                return
                            name = event.type.name
                            if name == 'NEW_ORDER':
                                adapter.event_order(event)
                            elif name == 'NEW_MESSAGE':
                                adapter.event_message(event)
                            elif name == 'ORDER_STATUS_CHANGED':
                                adapter.event_status(event)
                    except Exception as error:
                        logging.error('Слушатель FunPay: %s', type(error).__name__)
                        stopping.wait(10)
            adapter.start()
            threading.Thread(target=events, name='funpay-events', daemon=True).start()
            threading.Thread(target=Admin(root).run, name='telegram-admin', daemon=True).start()
            print('Auto Telegram Emoji запущен. Для остановки: Ctrl+C.')
            stopping.wait()
            server.shutdown()
            adapter.executor.shutdown(wait=True, cancel_futures=True)
        return 0
    except (ValueError, OSError, KeyError) as error:
        print('Ошибка настройки:', str(error))
        return 1
if __name__ == '__main__':
    raise SystemExit(main())
