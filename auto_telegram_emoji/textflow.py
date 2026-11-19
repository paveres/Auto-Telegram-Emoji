__author__ = '@paveres'
__channel__ = 'https://t.me/g_plugins'
__contact__ = 'https://t.me/paveres'
import copy

def value(data, position):
    key = str(position)
    if key in data.get('assign', {}):
        return data.get('text2', data.get('nick', '')) if data['assign'][key] == 2 else data.get('nick', '')
    if data.get('individual_texts'):
        return data.get('texts', {}).get(key, '')
    return data.get('nick', '')

def summary(data):
    values = {value(data, i) for i in range(1, len(data['cart']) + 1)}
    if len(values) == 1:
        return next(iter(values)) or 'без изменений'
    return 'индивидуальные тексты'

def open_menu(engine, order):
    d = order['data']
    if not d.get('individual_texts'):
        d['texts'] = {str(i): value(d, i) for i in range(1, len(d['cart']) + 1)}
        d['individual_texts'] = True
    _, pages, _ = engine.render.selected(order, True)
    engine.photos(order, 'text-choices', pages)
    order['stage'] = 'text_pick'
    lines = [str(i) + '. Эмодзи №' + str(i) + ' — ' + (value(d, i) or 'без изменений') for i in range(1, len(d['cart']) + 1)]
    engine.emit(order, 'text-choose', '💙【 Текст для эмодзи 】\n\n' + '\n'.join(lines) + '\n\nВведите номер эмодзи, чтобы задать текст.\nГотово — перейти к предпросмотру.')

def handle(engine, order, text):
    d = order['data']
    stage = order['stage']
    if stage not in {'text_pick', 'text_value'}:
        return False
    if text.startswith('!') and text not in {'!назад', '!отмена', '!готово'}:
        return False
    if text in {'!назад', '!отмена'}:
        if stage == 'text_value':
            open_menu(engine, order)
        else:
            finish(engine, order)
    elif stage == 'text_pick':
        if text in {'!готово', '+', '-', '−'}:
            finish(engine, order)
        elif text.isdigit() and 1 <= int(text) <= len(d['cart']):
            d['text_target'] = int(text)
            order['stage'] = 'text_value'
            engine.emit(order, 'text-input', 'Введите текст для эмодзи №' + text + '.\nДо 16 символов.\n\n− — оставить без изменения.')
    elif text in {'-', '−'}:
        open_menu(engine, order)
    elif not text.startswith('!'):
        from .vector import outlines
        outlines(text, engine.cat.base / 'fonts')
        candidate = copy.deepcopy(order)
        n = candidate['data']['text_target']
        candidate['data'].setdefault('texts', {})[str(n)] = text
        candidate['data'].setdefault('assign', {}).pop(str(n), None)
        candidate['data']['nick'] = next((v for v in candidate['data']['texts'].values() if v), 'EMOJI')
        _, pages, _ = engine.render.selected(candidate, True)
        from .editor import snapshot
        old = snapshot(d)
        d.update(candidate['data'])
        history = d.setdefault('undo', [])
        history.append(old)
        del history[:-20]
        engine.photos(order, 'text-updated', pages)
        order['stage'] = 'text_pick'
        engine.emit(order, 'text-saved', 'Текст для эмодзи №' + str(n) + ' сохранён.\n\nВведите номер другого эмодзи или «готово».')
    return True

def finish(engine, order):
    d = order['data']
    d['nick'] = next((value(d, i) for i in range(1, len(d['cart']) + 1) if value(d, i)), d.get('nick') or 'EMOJI')
    engine.preview(order)
