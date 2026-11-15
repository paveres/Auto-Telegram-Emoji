__author__ = '@justmeth'
__channel__ = 'https://t.me/g_plugins'
__contact__ = 'https://t.me/justmeth'
import ast, io, re, tokenize, json, sys
from pathlib import Path

def check(root):
    errors = []
    python_files = []
    for folder in ['auto_telegram_emoji', 'FunPayAPI', 'tests', 'scripts']:
        python_files.extend((root / folder).rglob('*.py'))
    for p in python_files:
        text = p.read_text(encoding='utf8')
        try:
            ast.parse(text)
        except SyntaxError:
            errors.append(str(p.relative_to(root)) + ': syntax')
        if any((t.type == tokenize.COMMENT for t in tokenize.generate_tokens(io.StringIO(text).readline))):
            errors.append(str(p.relative_to(root)) + ': comments')
        allowed = set(sys.stdlib_module_names) | {'auto_telegram_emoji', 'FunPayAPI', 'PIL', 'fontTools', 'rlottie_python', 'imageio_ffmpeg', 'dotenv', 'requests', 'requests_toolbelt', 'bs4', 'lxml', 'check_release'}
        for node in ast.walk(ast.parse(text)):
            imports = [x.name for x in node.names] if isinstance(node, ast.Import) else [node.module] if isinstance(node, ast.ImportFrom) and (not node.level) else []
            for name in imports:
                if name and name.split('.')[0] not in allowed and (not name.startswith('test_')):
                    errors.append(str(p.relative_to(root)) + ': external import ' + name)
        if re.search('\\b(?:ghp_[A-Za-z0-9]{25,}|\\d{8,12}:AA[A-Za-z0-9_-]{25,})', text):
            errors.append(str(p.relative_to(root)) + ': secret')
    if errors:
        raise ValueError('\n'.join(errors))
    return {'python_files': len(python_files), 'comments': 0, 'private_dependencies': 0, 'tokens': 0}
if __name__ == '__main__':
    print(json.dumps(check(Path(__file__).resolve().parents[1]), ensure_ascii=False))
