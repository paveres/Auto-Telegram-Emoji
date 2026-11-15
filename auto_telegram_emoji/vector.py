__author__ = '@justmeth'
__channel__ = 'https://t.me/g_plugins'
__contact__ = 'https://t.me/justmeth'
import copy, gzip, json, unicodedata, math
from pathlib import Path
from functools import lru_cache
from fontTools.ttLib import TTFont
from fontTools.pens.basePen import BasePen
from fontTools.varLib.instancer import instantiateVariableFont

class Pen(BasePen):

    def __init__(self, glyphs):
        super().__init__(glyphs)
        self.paths = []
        self.path = None

    def _moveTo(self, p):
        self.path = {'v': [[p[0], -p[1]]], 'i': [[0, 0]], 'o': [[0, 0]], 'c': True}

    def _lineTo(self, p):
        self.path['v'].append([p[0], -p[1]])
        self.path['i'].append([0, 0])
        self.path['o'].append([0, 0])

    def _curveToOne(self, a, b, c):
        old = self.path['v'][-1]
        self.path['o'][-1] = [a[0] - old[0], -a[1] - old[1]]
        self.path['v'].append([c[0], -c[1]])
        self.path['i'].append([b[0] - c[0], -b[1] + c[1]])
        self.path['o'].append([0, 0])

    def _qCurveToOne(self, b, c):
        a = self._getCurrentPoint()
        self._curveToOne((a[0] + 2 * (b[0] - a[0]) / 3, a[1] + 2 * (b[1] - a[1]) / 3), (c[0] + 2 * (b[0] - c[0]) / 3, c[1] + 2 * (b[1] - c[1]) / 3), c)

    def _closePath(self):
        if len(self.path['v']) > 1 and self.path['v'][-1] == self.path['v'][0]:
            self.path['i'][0] = self.path['i'].pop()
            self.path['v'].pop()
            self.path['o'].pop()
        if len(self.path['v']) > 1:
            self.paths.append(self.path)

    def _endPath(self):
        self._closePath()

@lru_cache(maxsize=4)
def fonts(folder, name='montserrat'):
    result = []
    for p in sorted(Path(folder).glob(name + '*.ttf')):
        font = TTFont(p)
        if 'fvar' in font:
            font = instantiateVariableFont(font, {'wght': 700}, inplace=True)
        result.append((font, font.getBestCmap(), font.getGlyphSet()))
    if not result:
        raise ValueError('Не найден шрифт Montserrat')
    return result

def outlines(text, folder, font='montserrat', spacing=0):
    text = unicodedata.normalize('NFC', text.strip())
    if not 1 <= len(text) <= 16 or any((unicodedata.category(c).startswith('C') for c in text)):
        raise ValueError('Ник должен содержать 1–16 печатных символов.')
    paths = []
    x = 0
    for ch in text:
        match = next(((f, c, g) for f, c, g in fonts(str(folder), font) if ord(ch) in c), None)
        if not match:
            raise ValueError('Шрифт не поддерживает символ: ' + ch)
        f, c, g = match
        name = c[ord(ch)]
        pen = Pen(g)
        g[name].draw(pen)
        for path in pen.paths:
            path['v'] = [[a + x, b] for a, b in path['v']]
            paths.append(path)
        x += f['hmtx'].metrics[name][0] + f['head'].unitsPerEm * spacing / 100
    if not paths:
        raise ValueError('Ник не может состоять только из пробелов.')
    return paths
GRADIENTS = [('#ffffff', '#5fb2ff'), ('#d6ecff', '#1f6bff'), ('#ffffff', '#ff4f7a'), ('#fff4b8', '#ffa600'), ('#ffe066', '#ff3b30'), ('#eafff5', '#25c96e'), ('#f1e6ff', '#9b4dff'), ('#ffffff', '#8e8e93')]
COLORS = ['original', '#1f6bff', '#16c6e8', '#f0285a', '#8a3dff', '#e39a00', '#18c06c', '#ff4d1a', '#8e8e93']

def rgb(s):
    return [int(s[i:i + 2], 16) / 255 for i in (1, 3, 5)]

def bbox(paths):
    points = [p for path in paths for p in path['v']]
    return (min((p[0] for p in points)), min((p[1] for p in points)), max((p[0] for p in points)), max((p[1] for p in points)))

def transform(source, text, font_folder, gradient=0, color=0, style=None):
    style = style or {}
    data = json.loads(gzip.decompress(Path(source).read_bytes()))
    new = outlines(text, font_folder, style.get('font', 'montserrat'), style.get('spacing', 0))
    angle = math.radians(style.get('rotate', 0))
    if angle:
        for p in new:
            for key in ('v', 'i', 'o'):
                p[key] = [[a * math.cos(angle) - b * math.sin(angle), a * math.sin(angle) + b * math.cos(angle)] for a, b in p[key]]
    nb = bbox(new)
    replaced = 0

    def visit(x):
        nonlocal replaced
        if isinstance(x, dict):
            items = x.get('it')
            if isinstance(items, list):
                old = [v for v in items if v.get('nm', '').startswith('emoji_glyph:')]
                if old:
                    if any((v.get('ty') != 'sh' or v.get('ks', {}).get('a') != 0 for v in old)):
                        raise ValueError('Неподдерживаемая анимация букв')
                    ob = bbox([v['ks']['k'] for v in old])
                    scale = min((ob[2] - ob[0]) / max(0.01, nb[2] - nb[0]), (ob[3] - ob[1]) / max(0.01, nb[3] - nb[1]))
                    if scale * (nb[3] - nb[1]) < (ob[3] - ob[1]) * 0.34:
                        raise ValueError('Ник слишком длинный для этого варианта. Сократите текст.')
                    dx = (ob[0] + ob[2]) / 2 - scale * (nb[0] + nb[2]) / 2
                    dy = (ob[1] + ob[3]) / 2 - scale * (nb[1] + nb[3]) / 2
                    factor = style.get('size', 100) / 100
                    scale *= factor
                    dx = (ob[0] + ob[2]) / 2 - scale * (nb[0] + nb[2]) / 2 + (ob[2] - ob[0]) * style.get('x', 0) / 100
                    dy = (ob[1] + ob[3]) / 2 - scale * (nb[1] + nb[3]) / 2 + (ob[3] - ob[1]) * style.get('y', 0) / 100
                    shapes = []
                    for path in new:
                        k = copy.deepcopy(path)
                        k['v'] = [[round(a * scale + dx, 2), round(b * scale + dy, 2)] for a, b in k['v']]
                        for key in ('i', 'o'):
                            k[key] = [[round(a * scale, 2), round(b * scale, 2)] for a, b in k[key]]
                        shapes.append({'ty': 'sh', 'nm': 'emoji_glyph', 'ks': {'a': 0, 'k': k}})
                    result = []
                    inserted = False
                    for v in items:
                        if v.get('nm', '').startswith('emoji_glyph:'):
                            if not inserted:
                                result.extend(shapes)
                                inserted = True
                        elif gradient and v.get('ty') in {'fl', 'gf'}:
                            a, b = GRADIENTS[gradient - 1]
                            result.append({'ty': 'gf', 'o': v.get('o', {'a': 0, 'k': 100}), 'r': v.get('r', 1), 't': 1, 's': {'a': 0, 'k': [ob[0], ob[1]]}, 'e': {'a': 0, 'k': [ob[0], ob[3]]}, 'g': {'p': 2, 'k': {'a': 0, 'k': [0, *rgb(a), 1, *rgb(b)]}}})
                        elif style.get('text_color') and v.get('ty') in {'fl', 'gf'}:
                            result.append({'ty': 'fl', 'c': {'a': 0, 'k': [*rgb(style['text_color']), 1]}, 'o': v.get('o', {'a': 0, 'k': 100}), 'r': 1})
                        else:
                            result.append(v)
                    if style.get('stroke_width', 0):
                        result.insert(max(0, len(result) - 1), {'ty': 'st', 'c': {'a': 0, 'k': [*rgb(style.get('stroke_color', '#000000')), 1]}, 'o': {'a': 0, 'k': 100}, 'w': {'a': 0, 'k': style['stroke_width']}, 'lc': 2, 'lj': 2})
                    x['it'] = result
                    replaced += 1
            for v in x.values():
                visit(v)
        elif isinstance(x, list):
            for v in x:
                visit(v)
    visit(data)
    if not replaced:
        raise ValueError('В шаблоне нет заменяемой надписи.')
    if style.get('theme'):
        from .gradients import theme
        theme(data, style['theme'], style.get('angle', 135), style.get('animated', True))
    if style.get('body_color'):

        def body(x):
            if isinstance(x, dict):
                if isinstance(x.get('it'), list) and (not any((v.get('nm') == 'emoji_glyph' for v in x['it']))):
                    for v in x['it']:
                        if v.get('ty') == 'fl':
                            v['c'] = {'a': 0, 'k': [*rgb(style['body_color']), 1]}
                for v in x.values():
                    body(v)
            elif isinstance(x, list):
                for v in x:
                    body(v)
        body(data)
    if color:
        target = rgb(COLORS[color])

        def paint(x):
            if isinstance(x, dict):
                if x.get('ty') in {'fl', 'st'} and x.get('c', {}).get('a') == 0:
                    c = x['c'].get('k', [])
                    if len(c) >= 3 and max((abs(c[i] - [168 / 255, 199 / 255, 239 / 255][i]) for i in range(3))) < 0.015:
                        x['c']['k'] = [*target, 1]
                for v in x.values():
                    paint(v)
            elif isinstance(x, list):
                for v in x:
                    paint(v)
        paint(data)
    data['tgs'] = 1
    raw = gzip.compress(json.dumps(data, separators=(',', ':'), ensure_ascii=False).encode(), mtime=0)
    if len(raw) > 65536:
        raise ValueError('Этот вариант с таким ником превышает размер TGS. Сократите ник.')
    return raw
