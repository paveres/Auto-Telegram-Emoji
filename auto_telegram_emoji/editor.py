__author__ = '@paveres'
__channel__ = 'https://t.me/g_plugins'
__contact__ = 'https://t.me/paveres'
import copy, re
from .parser import numbers
from .gradients import THEMES
FONTS = ['montserrat', 'unbounded', 'russo', 'lobster', 'pixel']
FIELDS = ('nick', 'text2', 'texts', 'individual_texts', 'assign', 'styles', 'style_global', 'gradient', 'color')
MENU = '💙【 Редактор 】\n1. Текст\n2. Второй текст\n3. Шрифт\n4. Цвет\n5. Градиент\n6. Размер\n7. Позиция\n8. Обводка\n9. Предпросмотр\n\nМожно указать позиции: !редактировать 1,3. Без номеров — весь набор.\nДругие команды: !поворот, !интервал, !копировать, !сравнить, !фон, !откат, !сброс, !стиль.'

def snapshot(d):
    return {k: copy.deepcopy(d.get(k)) for k in FIELDS}

def restore(d, s):
    for k, v in s.items():
        if v is None:
            d.pop(k, None)
        else:
            d[k] = copy.deepcopy(v)

def selected(d):
    return d.get('edit_targets', list(range(1, len(d['cart']) + 1)))

def style(d, key, value):
    d.setdefault('styles', {})
    for n in selected(d):
        d['styles'].setdefault(str(n), {})[key] = value

def preview(e, o, old=None):
    if old is not None:
        history = o['data'].setdefault('undo', [])
        history.append(old)
        del history[:-20]
    e.preview(o)

def handle(e, o, text):
    d = o['data']
    stage = o['stage']
    parts = text.split(maxsplit=1)
    cmd = parts[0] if parts else ''
    arg = parts[1] if len(parts) > 1 else ''
    commands = {'!редактировать', '!текст', '!текст2', '!назначить', '!шрифт', '!цвет', '!градиент', '!размер', '!позиция', '!поворот', '!обводка', '!интервал', '!копировать', '!пример', '!сравнить', '!фон', '!откат', '!сброс', '!стиль'}
    if stage == 'edit_menu' and text.isdigit():
        menu = ['!текст', '!текст2', '!шрифт', '!цвет', '!градиент', '!размер', '!позиция', '!обводка', '!пример']
        n = int(text)
        if not 1 <= n <= len(menu):
            raise ValueError('Выберите пункт 1–9.')
        cmd = menu[n - 1]
        arg = ''
    elif stage.startswith('editor_') and (not text.startswith('!')):
        cmd = '!' + stage.removeprefix('editor_')
        arg = text
    elif cmd not in commands:
        return False
    allowed = {'preview', 'edit_menu', 'editor_текст', 'editor_текст2', 'editor_шрифт', 'editor_цвет', 'editor_градиент', 'editor_размер', 'editor_позиция', 'editor_поворот', 'editor_обводка', 'editor_интервал', 'editor_копировать', 'editor_назначить', 'editor_стиль', 'editor_фон'}
    if stage not in allowed:
        raise ValueError('Редактор доступен после подтверждения вариантов и ввода первого текста. !статус — текущий этап.')
    if cmd == '!редактировать':
        d['edit_targets'] = numbers(arg, len(d['cart'])) if arg else list(range(1, len(d['cart']) + 1))
        o['stage'] = 'edit_menu'
        e.emit(o, 'editor', MENU)
        return True
    old = snapshot(d)
    if cmd == '!текст' and (not arg):
        from .textflow import open_menu
        open_menu(e, o)
        return True
    if cmd in {'!пример', '!сравнить', '!фон'}:
        if cmd == '!сравнить' and d.get('undo'):
            before = copy.deepcopy(o)
            restore(before['data'], d['undo'][-1])
            before['data']['rev'] = str(d['rev']) + '-before'
            _, pages, _ = e.render.selected(before, True)
            e.photos(o, 'before', pages)
            e.emit(o, 'before-label', 'До изменения. Далее — текущий результат.')
        if cmd == '!фон':
            _, pages, _ = e.render.selected(o, True)
            e.photos(o, 'dark', pages)
            e.photos(o, 'light', e.render.light_cards(o))
            e.emit(o, 'background', 'Проверка на тёмном и светлом фоне. Фон самого TGS остаётся прозрачным.')
            o['stage'] = 'preview'
        else:
            e.preview(o)
        return True
    if cmd == '!откат':
        if not d.get('undo'):
            raise ValueError('Нет предыдущего изменения.')
        restore(d, d['undo'].pop())
        e.preview(o)
        return True
    if cmd == '!сброс':
        for n in selected(d):
            d.setdefault('styles', {}).pop(str(n), None)
        d.pop('style_global', None)
        d['color'] = 0
        d['gradient'] = 0
        preview(e, o, old)
        return True
    if cmd == '!стиль':
        if not arg:
            o['stage'] = 'editor_стиль'
            e.emit(o, 'style-help', 'Введите «сохранить» или «применить». Сохраняется оформление без ваших текстов.')
            return True
        if arg.lower() in {'сохранить', 'save', 'сохрани'}:
            first = selected(d)[0]
            saved = {**d.get('style_global', {}), **d.get('styles', {}).get(str(first), {})}
            e.wallet.style(o['buyer'], saved)
            o['stage'] = 'preview'
            e.emit(o, 'style-saved', 'Оформление сохранено для следующих заказов.\n!редактор — настройки\n!предпросмотр — результат и подтверждение')
            return True
        if arg.lower() not in {'применить', 'load', 'загрузить'}:
            raise ValueError('Введите «сохранить» или «применить».')
        saved = e.wallet.style(o['buyer'])
        if saved is None:
            raise ValueError('У вас пока нет сохранённого стиля.')
        for n in selected(d):
            d.setdefault('styles', {})[str(n)] = copy.deepcopy(saved)
        preview(e, o, old)
        return True
    prompts = {'!текст': 'Введите первый текст, до 16 символов.', '!текст2': 'Введите второй текст, до 16 символов. «удалить» — убрать второй текст.', '!назначить': 'Формат: !назначить 2 1,3 — второй текст на позиции 1 и 3. Первый текст по умолчанию на остальных.', '!шрифт': '\n'.join((f'{i}. {f}' for i, f in enumerate(FONTS, 1))), '!цвет': 'Формат: текст #FFFFFF или фигура #FF0000. Можно названия: белый, чёрный, красный, жёлтый, синий, зелёный, розовый, фиолетовый.', '!градиент': '\n'.join((f'{i}. {t[0]}' for i, t in enumerate(THEMES, 1))) + '\n0. Оригинал\nМожно дописать угол: 1 45. Анимация самого эмодзи сохраняется.', '!размер': 'Введите размер текста: 50–120 процентов.', '!позиция': 'Введите X Y от −20 до 20 процентов, например 0 -10 — выше.', '!поворот': 'Введите угол от −45 до 45 градусов.', '!обводка': 'Введите толщину 0–5 и цвет, например 2 #000000. 0 — без обводки.', '!интервал': 'Введите интервал между буквами: от −5 до 15.', '!копировать': 'Введите исходную позицию и получателей: 1 2,3.'}
    if cmd == '!текст2' and o.get('paid_qty', o['qty']) == 1:
        raise ValueError('Для одного оплаченного эмодзи доступен один текст.')
    if not arg:
        o['stage'] = 'editor_' + cmd[1:]
        e.emit(o, 'edit-prompt', prompts[cmd] + '\n!отмена — вернуться к предпросмотру.')
        if cmd in {'!шрифт', '!градиент'}:
            samples = []
            first = selected(d)[0]
            c, n = d['cart'][first - 1]
            from .vector import transform
            for i in range(len(FONTS) if cmd == '!шрифт' else len(THEMES)):
                test = {'font': FONTS[i]} if cmd == '!шрифт' else {'theme': i + 1, 'text_color': '#FFFFFF'}
                try:
                    sample = transform(e.cat.get(c, n), d['nick'], e.cat.base / 'fonts', style=test)
                except ValueError:
                    sample = transform(e.cat.get(c, n), 'DEMO', e.cat.base / 'fonts', style=test)
                samples.append(sample)
            e.photos(o, 'edit-options', e.render.cards(samples, e.render.folder / 'orders' / o['id'] / f"options-{d['rev']}"))
        return True
    if cmd in {'!текст', '!текст2'}:
        if cmd == '!текст2' and arg.lower() in {'удалить', 'убрать', 'remove', '0'}:
            d.pop('text2', None)
            d['assign'] = {}
        else:
            from .vector import outlines
            outlines(arg, e.cat.base / 'fonts')
            d['nick' if cmd == '!текст' else 'text2'] = arg
            if cmd == '!текст' and d.get('individual_texts'):
                for n in selected(d):
                    d.setdefault('texts', {})[str(n)] = arg
                    d.setdefault('assign', {}).pop(str(n), None)
            if cmd == '!текст2' and (not any((v == 2 for v in d.get('assign', {}).values()))):
                targets = selected(d)
                if len(targets) == len(d['cart']):
                    targets = [len(d['cart'])]
                for n in targets:
                    d.setdefault('assign', {})[str(n)] = 2
                e.emit(o, 'text2-assigned', 'Второй текст назначен позициям: ' + ', '.join(map(str, targets)) + '.\n!назначить 2 1,3 — изменить назначение.')
    elif cmd == '!назначить':
        p = arg.split(maxsplit=1)
        if len(p) != 2 or p[0] not in {'1', '2'}:
            raise ValueError(prompts[cmd])
        if p[0] == '2' and (not d.get('text2')):
            raise ValueError('Сначала задайте второй текст: !текст2.')
        for n in numbers(p[1], len(d['cart'])):
            d.setdefault('assign', {})[str(n)] = int(p[0])
    elif cmd == '!шрифт':
        font = FONTS[int(arg) - 1] if arg.isdigit() and 1 <= int(arg) <= len(FONTS) else arg.lower()
        if font not in FONTS:
            raise ValueError('Выберите шрифт 1–5.')
        style(d, 'font', font)
    elif cmd == '!цвет':
        p = arg.split()
        names = {'белый': '#FFFFFF', 'черный': '#000000', 'чёрный': '#000000', 'красный': '#FF2638', 'желтый': '#FFD600', 'жёлтый': '#FFD600', 'синий': '#268AFF', 'зеленый': '#22D980', 'зелёный': '#22D980', 'розовый': '#FF4FA3', 'фиолетовый': '#A85BFF'}
        if len(p) != 2 or p[0].lower() not in {'текст', 'фигура', 'text', 'body'}:
            raise ValueError(prompts[cmd])
        color = names.get(p[1].lower(), p[1])
        if not re.fullmatch('#[0-9a-fA-F]{6}', color):
            raise ValueError('Цвет должен иметь вид #RRGGBB.')
        style(d, 'text_color' if p[0] in {'текст', 'text'} else 'body_color', color)
    elif cmd == '!градиент':
        p = arg.split()
        if not p[0].isdigit() or not 0 <= int(p[0]) <= len(THEMES):
            raise ValueError('Выберите градиент 0–9.')
        style(d, 'theme', int(p[0]))
        style(d, 'animated', not any((x.lower() in {'статичный', 'static'} for x in p)))
        style(d, 'body_color', None)
        style(d, 'text_color', '#FFFFFF')
        d['gradient'] = 0
        if len(p) > 1 and p[1].lstrip('-').isdigit():
            style(d, 'angle', int(p[1]) % 360)
    elif cmd == '!копировать':
        p = arg.split(maxsplit=1)
        if len(p) != 2 or not p[0].isdigit() or (not 1 <= int(p[0]) <= len(d['cart'])):
            raise ValueError(prompts[cmd])
        source = {**d.get('style_global', {}), **d.get('styles', {}).get(p[0], {})}
        for n in numbers(p[1], len(d['cart'])):
            d.setdefault('styles', {})[str(n)] = copy.deepcopy(source)
    else:
        p = arg.split()
        try:
            values = [float(x.replace(',', '.')) for x in p[:2 if cmd == '!позиция' else 1]]
        except ValueError:
            raise ValueError(prompts[cmd])
        bounds = {'!размер': (50, 120), '!поворот': (-45, 45), '!интервал': (-5, 15), '!обводка': (0, 5), '!позиция': (-20, 20)}
        lo, hi = bounds[cmd]
        if not values or any((not lo <= v <= hi for v in values)):
            raise ValueError(prompts[cmd])
        if cmd == '!позиция':
            if len(values) != 2:
                raise ValueError(prompts[cmd])
            style(d, 'x', values[0])
            style(d, 'y', values[1])
        else:
            style(d, {'!размер': 'size', '!поворот': 'rotate', '!интервал': 'spacing', '!обводка': 'stroke_width'}[cmd], values[0])
        if cmd == '!обводка' and len(p) > 1:
            if not re.fullmatch('#[0-9a-fA-F]{6}', p[1]):
                raise ValueError('Укажите цвет обводки #RRGGBB.')
            style(d, 'stroke_color', p[1])
    preview(e, o, old)
    return True
