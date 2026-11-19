__author__ = '@paveres'
__channel__ = 'https://t.me/g_plugins'
__contact__ = 'https://t.me/paveres'
import math, copy
THEMES = [('Чёрно-красный', '#ff2d3d', '#ffb3b8'), ('Чёрно-жёлтый', '#ffd600', '#fff7ad'), ('Чёрно-золотой', '#ffc233', '#fff3c4'), ('Чёрно-синий', '#2f8bff', '#c4e0ff'), ('Чёрно-зелёный', '#22e07a', '#c6ffe0'), ('Чёрно-фиолетовый', '#a85bff', '#ecd9ff'), ('Чёрно-розовый', '#ff4fa3', '#ffd0e8'), ('Чёрно-бирюзовый', '#22d3ee', '#d0f7ff'), ('Чёрно-серебряный', '#c9ccd3', '#ffffff')]

def rgb(s):
    return [int(s[i:i + 2], 16) / 255 for i in (1, 3, 5)]

def st(x):
    return {'a': 0, 'k': x}

def theme(data, index, angle=135, animated=False):
    animated = False
    if not index:
        return data
    _, main, highlight = THEMES[index - 1]
    c = rgb(main)
    hi = rgb(highlight)
    black = [0.02] * 3
    dark = [0.28 * v + 0.72 * 0.02 for v in c]
    stops = []
    for pos, col in zip([0, 0.18, 0.36, 0.5, 0.64, 0.82, 1], [black, dark, c, hi, c, dark, black]):
        stops.extend([pos, *col])
    ip = data.get('ip', 0)
    op = data.get('op', 180)

    def orbit(phase, cx=0, cy=0, radius=280):
        if not animated:
            a = math.radians(angle + phase)
            return st([round(cx + radius * math.cos(a), 2), round(cy + radius * math.sin(a), 2)])
        frames = [{'t': ip + (op - ip) * n / 8, 's': [round(cx + radius * math.cos(math.radians(angle + phase + 360 * n / 8)), 2), round(cy + radius * math.sin(math.radians(angle + phase + 360 * n / 8)), 2)], 'i': {'x': [0.833], 'y': [0.833]}, 'o': {'x': [0.167], 'y': [0.167]}} for n in range(9)]
        for i, frame in enumerate(frames[:-1]):
            frame['e'] = frames[i + 1]['s']
        return {'a': 1, 'k': frames}

    def walk(x):
        if isinstance(x, dict):
            for prop in ('it', 'shapes'):
                if not isinstance(x.get(prop), list):
                    continue
                items = x[prop]
                is_text = any((v.get('nm') == 'emoji_glyph' for v in items))
                points = [p for v in items if v.get('ty') == 'sh' and isinstance(v.get('ks', {}).get('k'), dict) for p in v['ks']['k'].get('v', [])]
                if points:
                    left = min((p[0] for p in points))
                    right = max((p[0] for p in points))
                    top = min((p[1] for p in points))
                    bottom = max((p[1] for p in points))
                    cx = (left + right) / 2
                    cy = (top + bottom) / 2
                    radius = max(right - left, bottom - top) * 0.65
                else:
                    cx = cy = 0
                    radius = 280
                if not is_text:
                    for i, v in enumerate(items):
                        if v.get('ty') not in {'fl', 'st', 'gf', 'gs'}:
                            continue
                        col = v.get('c', {}).get('k', [])
                        if isinstance(col, list) and col and isinstance(col[0], dict):
                            col = col[0].get('s', [])
                        lum = sum(col[:3]) / 3 if isinstance(col, list) and len(col) >= 3 and all((isinstance(c, (int, float)) for c in col[:3])) else 0.5
                        stroke = v['ty'] in {'st', 'gs'}
                        shine = stroke or lum > 0.35
                        ramp = {'p': 7, 'k': st(stops)} if shine else {'p': 3, 'k': st([0, 0, 0, 0, 0.5, 0.06, 0.07, 0.06, 1, 0, 0, 0])}
                        a = math.radians(angle)
                        start = st([cx + radius * math.cos(a), cy + radius * math.sin(a)])
                        end = st([cx - radius * math.cos(a), cy - radius * math.sin(a)])
                        if animated and shine:
                            keys = []
                            for phase in range(5):
                                values = list(stops)
                                shift = 0.09 * math.sin(phase * math.pi / 2)
                                for point in range(1, 6):
                                    values[point * 4] += shift
                                keys.append({'t': ip + (op - ip) * phase / 4, 's': values, 'i': {'x': [0.667], 'y': [1]}, 'o': {'x': [0.333], 'y': [0]}})
                            for j, key in enumerate(keys[:-1]):
                                key['e'] = keys[j + 1]['s']
                            ramp = {'p': 7, 'k': {'a': 1, 'k': keys}}
                        new = {'ty': 'gs' if stroke else 'gf', 'o': copy.deepcopy(v.get('o', st(100))), 'r': v.get('r', 1), 't': 1, 'g': ramp, 's': start, 'e': end, 'h': st(0), 'a': st(0)}
                        if stroke:
                            new.update(w=copy.deepcopy(v.get('w', st(4))), lc=v.get('lc', 2), lj=v.get('lj', 2), ml=v.get('ml', 4))
                        items[i] = new
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    walk(data)
    return data
