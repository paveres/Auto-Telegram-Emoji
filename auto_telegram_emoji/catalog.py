__author__ = '@justmeth'
__channel__ = 'https://t.me/g_plugins'
__contact__ = 'https://t.me/justmeth'
import json
from pathlib import Path
NAMES = {'characters': 'Персонажи', 'classic': 'Классика', 'finance': 'Финансы', 'gift': 'Подарки', 'love': 'Любовь', 'one': 'Ван', 'other': 'Разное'}

class Catalog:

    def __init__(self, root):
        private = Path(root) / 'data/assets'
        self.base = private if (private / 'catalog.json').is_file() else Path(root) / 'assets'
        self.data = json.loads((self.base / 'catalog.json').read_text(encoding='utf-8'))

    def collections(self):
        return list(self.data)

    def items(self, c):
        return self.data[c]

    def get(self, c, n):
        rows = self.items(c)
        if n < 1 or n > len(rows):
            raise ValueError('Нет такого варианта')
        p = (self.base / rows[n - 1]).resolve()
        if self.base.resolve() not in p.parents or p.suffix != '.tgs':
            raise ValueError('Некорректный путь шаблона')
        return p

    def label(self, c, n):
        return NAMES[c] + ' №' + str(n)
