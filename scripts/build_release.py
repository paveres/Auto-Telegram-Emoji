__author__ = '@justmeth'
__channel__ = 'https://t.me/g_plugins'
__contact__ = 'https://t.me/justmeth'
import json, zipfile, hashlib
from pathlib import Path
from check_release import check

def main():
    root = Path(__file__).resolve().parents[1]
    result = check(root)
    dist = root / 'dist'
    dist.mkdir(exist_ok=True)
    output = dist / 'Auto-Telegram-Emoji-1.0.1.zip'
    names = ['auto_telegram_emoji', 'FunPayAPI', 'assets', 'docs', 'third_party', 'scripts', 'tests']
    files = []
    for name in names:
        for p in (root / name).rglob('*'):
            if p.is_file() and '__pycache__' not in p.parts and (p.suffix != '.pyc'):
                files.append(p)
    for name in ['README.md', 'LICENSE', 'requirements.txt', 'requirements-lock.txt', 'pyproject.toml', '.env.example', '.gitignore', 'start.bat', 'install.bat', 'start.sh', 'scripts/setup.py', 'config/app.example.json']:
        p = root / name
        if p.is_file():
            files.append(p)
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as z:
        for p in sorted(set(files)):
            z.write(p, p.relative_to(root).as_posix())
    with zipfile.ZipFile(output) as z:
        assert not any((n == '.env' or n.startswith(('data/', '.venv/')) or n == 'config/app.json' for n in z.namelist()))
    result.update(files=len(files), archive=output.name, sha256=hashlib.sha256(output.read_bytes()).hexdigest())
    (dist / 'release-check.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf8')
    print(json.dumps(result, ensure_ascii=False))
if __name__ == '__main__':
    main()
