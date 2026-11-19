__author__ = '@paveres'
__channel__ = 'https://t.me/g_plugins'
__contact__ = 'https://t.me/paveres'
import gzip, json, shutil, zlib, tempfile, time
from pathlib import Path

def import_assets(source, destination):
    source = Path(source).resolve()
    destination = Path(destination).resolve()
    if source == destination or source in destination.parents:
        raise ValueError('Выберите внешнюю папку с шаблонами')
    if (source / 'tgs').is_dir():
        source = source / 'tgs'
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_symlink():
        raise ValueError('Папка назначения не должна быть ссылкой')
    staging = Path(tempfile.mkdtemp(prefix='assets-import-', dir=destination.parent)).resolve()
    rows = {}
    allowed = {'characters', 'classic', 'finance', 'gift', 'love', 'one', 'other'}
    for collection in sorted(allowed):
        files = sorted((source / collection).glob('*.tgs')) if (source / collection).is_dir() else []
        if not files:
            continue
        rows[collection] = []
        for p in files[:25]:
            raw = p.read_bytes()
            if len(raw) > 65536:
                raise ValueError('Слишком большой TGS: ' + p.name)
            decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
            body = decoder.decompress(raw, 4 * 1024 * 1024 + 1)
            if len(body) > 4 * 1024 * 1024 or not decoder.eof:
                raise ValueError('Некорректный TGS: ' + p.name)
            data = json.loads(body)

            def editable(node):
                if isinstance(node, dict):
                    return str(node.get('nm', '')).startswith('emoji_glyph:') or any((editable(v) for v in node.values()))
                return isinstance(node, list) and any((editable(v) for v in node))
            if not editable(data):
                raise ValueError('В шаблоне нет заменяемой надписи: ' + p.name)
            relative = Path('tgs') / collection / p.name
            dest = staging / relative
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(p, dest)
            rows[collection].append(relative.as_posix())
    if not rows:
        raise ValueError('Нужны подпапки classic, love, characters и другие коллекции с TGS')
    (staging / 'catalog.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf8')
    assert staging.parent == destination.parent
    if destination.exists():
        backup = destination.with_name('assets-backup-' + str(time.time_ns())).resolve()
        assert backup.parent == destination.parent
        destination.rename(backup)
    staging.rename(destination)
    return sum(map(len, rows.values()))
