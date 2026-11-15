__author__ = '@justmeth'
__channel__ = 'https://t.me/g_plugins'
__contact__ = 'https://t.me/justmeth'
import os, sys, json, zipfile
from pathlib import Path
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
os.chdir(root)
os.environ['AUTO_EMOJI_ROOT'] = str(root)
from auto_telegram_emoji.catalog import Catalog
from auto_telegram_emoji.render import Renderer

def main():
    order = {'id': 'OFFLINEDEMO', 'qty': 3, 'data': {'cart': [['classic', 1], ['classic', 2], ['classic', 3]], 'nick': 'JUSTMETH', 'individual_texts': True, 'texts': {'1': 'JUSTMETH', '2': 'G PLUGINS', '3': 'ТЕСТ'}, 'rev': 1, 'color': 0, 'gradient': 0}}
    pages, video, archive = Renderer(root, Catalog(root)).build(order, True)
    assert all((p.is_file() for p in [*pages, video, archive]))
    with zipfile.ZipFile(archive) as z:
        assert len(z.namelist()) == 3 and z.testzip() is None
    result = {'photos': len(pages), 'video_bytes': video.stat().st_size, 'tgs_files': 3, 'network_used': False}
    (root / 'data/smoke-render.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf8')
    print(json.dumps(result))
if __name__ == '__main__':
    main()
