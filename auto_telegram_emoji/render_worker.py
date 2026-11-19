__author__ = '@paveres'
__channel__ = 'https://t.me/g_plugins'
__contact__ = 'https://t.me/paveres'
import os, sys, json
from pathlib import Path

def main():
    request = Path(sys.argv[1])
    response = Path(sys.argv[2])
    data = json.loads(request.read_text(encoding='utf8'))
    if os.name == 'posix':
        import resource
        os.nice(15)
        if hasattr(os, 'sched_getaffinity'):
            os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
        resource.setrlimit(resource.RLIMIT_AS, (768 * 1024 * 1024, 768 * 1024 * 1024))
        resource.setrlimit(resource.RLIMIT_CPU, (600, 630))
    try:
        from .catalog import Catalog
        from .render import Renderer
        r = Renderer(data['root'], Catalog(data['root']))
        r.folder = Path(data['folder'])
        if data.get('action', 'build') == 'cards':
            paths = r.cards([bytes.fromhex(raw) for raw in data['raws']], Path(data['path']), data.get('labels'), data.get('background', 'black'))
            result = {'pages': [str(p) for p in paths]}
        else:
            pages, video, archive = r.build(data['order'], data['final'])
            result = {'pages': [str(p) for p in pages], 'video': str(video), 'archive': str(archive) if archive else None}
        response.write_text(json.dumps(result), encoding='utf8')
    except Exception as e:
        response.write_text(json.dumps({'error': str(e)[:300], 'validation': isinstance(e, ValueError)}), encoding='utf8')
        return 1
    return 0
if __name__ == '__main__':
    raise SystemExit(main())
