__author__ = '@paveres'
__channel__ = 'https://t.me/g_plugins'
__contact__ = 'https://t.me/paveres'
import re
YES = {'+', 'да', 'д', 'ага', 'угу', 'ок', 'окей', 'подтверждаю', 'подтвердить', 'согласен', 'дап', 'yes', 'y', 'yeah', 'yep', 'ok', 'okay'}
NO = {'-', '−', 'нет', 'н', 'не', 'неа', 'ноу', 'отказываюсь', 'no', 'n', 'nope', 'nah'}
ALIASES = {'!саппорт': ['саппорт', 'сапорт', 'поддержка', '!поддержка', 'support'], '!меню': ['меню', 'команды', '!команды', 'получить команды', 'список команд', 'получить список команд', 'help', 'menu', 'помощь', '!помощь'], '!коллекции': ['коллекции', 'коллекция', 'каталог', 'collections', 'catalog'], '!корзина': ['корзина', 'мой выбор', 'выбранное', 'cart'], '!добавить': ['добавить', 'добавь', 'добавление', 'add'], '!убрать': ['убрать', 'удалить', 'убери', 'remove', 'del'], '!смена': ['смена', 'сменить', 'заново', 'поменять выбор', 'change'], '!редактировать': ['редактировать', 'редактор', '!редактор', 'изменить', 'edit'], '!текст': ['текст', 'тексты', '!тексты', 'ник', 'никнейм', 'text', 'nickname'], '!текст2': ['текст2', 'второй текст', 'ник2', 'text2'], '!назначить': ['назначить', 'распределить', 'assign'], '!шрифт': ['шрифт', 'шрифты', 'font'], '!цвет': ['цвет', 'цвета', 'color', 'colour'], '!градиент': ['градиент', 'градиенты', 'gradient'], '!размер': ['размер', 'масштаб', 'size'], '!позиция': ['позиция', 'положение', 'сдвиг', 'position'], '!поворот': ['поворот', 'наклон', 'rotate'], '!обводка': ['обводка', 'контур', 'stroke'], '!интервал': ['интервал', 'расстояние', 'spacing'], '!копировать': ['копировать', 'скопировать', 'copy'], '!пример': ['пример', 'превью', 'предпросмотр', '!предпросмотр', 'посмотреть', 'preview'], '!сравнить': ['сравнить', 'сравнение', 'до после', 'compare'], '!фон': ['фон', 'background'], '!откат': ['откат', 'отменить изменение', 'undo'], '!сброс': ['сброс', 'сбросить', 'reset'], '!стиль': ['стиль', 'мой стиль', 'style'], '!бонус': ['бонус', 'бонусы', 'баланс бонусов', 'bonus'], '!статус': ['статус', 'заказ', 'status'], '!продолжить': ['продолжить', 'продолжим', 'resume'], '!файлы': ['файлы', 'архив', 'скачать', 'zip', 'files'], '!пак': ['пак', 'паки', 'мой пак', 'pack'], '!мои': ['мои', 'мои эмодзи', 'мои наборы', 'история', 'история эмодзи', 'мои файлы', 'my', 'history'], '!бэк': ['бэк', 'бек', 'вернуть деньги', 'возврат', 'refund'], '!продавец': ['продавец', 'человек', 'оператор', 'seller'], '!назад': ['назад', 'вернуться', 'back'], '!отмена': ['отмена', 'отменить', 'cancel'], '!готово': ['готово', 'готов', 'done']}
CONFIRM = {'support_confirm', 'confirm', 'preview', 'style_confirm', 'refund_confirm', 'wallet_confirm', 'wallet_use_confirm', 'archive_confirm'}
TEXT_STAGES = {'nick', 'nick_edit', 'editor_текст', 'editor_текст2', 'text_value'}

def normalize(text, stage=''):
    raw = text.strip()
    fold = re.sub('\\s+', ' ', raw.casefold()).replace('ё', 'е')
    if stage in CONFIRM:
        if fold in YES:
            return '+'
        if fold in NO:
            return '-'
    entries = []
    for command, aliases in ALIASES.items():
        for alias in [command, command[1:], *aliases]:
            entries.append((alias, command))
            if not alias.startswith('!'):
                entries.append(('!' + alias, command))
    for alias, command in sorted(entries, key=lambda x: len(x[0]), reverse=True):
        if fold == alias:
            return command
        if fold.startswith(alias + ' ') and (raw.startswith(('!', '/')) or stage not in TEXT_STAGES):
            return command + ' ' + raw[len(alias):].strip()
    if raw.startswith('/'):
        return normalize('!' + raw[1:], stage)
    return raw
