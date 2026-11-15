__author__ = '@justmeth'
__channel__ = 'https://t.me/g_plugins'
__contact__ = 'https://t.me/justmeth'
import re, unicodedata

def numbers(text, maximum=50):
    text = unicodedata.normalize('NFKC', text.replace('№', '')).strip().lower()
    if len(text) > 500:
        raise ValueError('Слишком длинный список.')
    text = re.sub('\\bи\\b', ',', text).replace('№', '').replace('–', '-').replace('—', '-')
    if not text or re.search('[^\\d\\s,;\\-]', text):
        raise ValueError('Пришлите номера, например: 1, 5, 47.')
    text = re.sub('\\s*-\\s*', '-', text)
    result = []
    for part in re.split('[\\s,;]+', text):
        if not part:
            continue
        if re.fullmatch('\\d+', part):
            values = [int(part)]
        elif re.fullmatch('\\d+-\\d+', part):
            a, b = map(int, part.split('-'))
            if not 1 <= a <= b <= maximum:
                raise ValueError(f'Доступны номера 1–{maximum}.')
            values = range(a, b + 1)
        else:
            raise ValueError('Не удалось разобрать список номеров.')
        for n in values:
            if not 1 <= n <= maximum:
                raise ValueError(f'Доступны номера 1–{maximum}.')
            if n not in result:
                result.append(n)
    if not result:
        raise ValueError('Список пуст.')
    return result
