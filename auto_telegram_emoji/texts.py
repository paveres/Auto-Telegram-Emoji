__author__ = '@justmeth'
__channel__ = 'https://t.me/g_plugins'
__contact__ = 'https://t.me/justmeth'
from .catalog import NAMES
STAGES = {'intro_pending': 'подготовка коллекций', 'catalog_pending': 'отправка вариантов', 'collection': 'выбор коллекции', 'select': 'выбор эмодзи', 'selection_action': 'добавление из коллекций', 'text_pick': 'выбор эмодзи для текста', 'text_value': 'ввод текста эмодзи', 'confirm': 'подтверждение вариантов', 'nick': 'ввод ника', 'nick_edit': 'изменение ника', 'preview': 'проверка результата', 'color': 'выбор цвета', 'gradient': 'выбор градиента', 'style_confirm': 'примерка оформления', 'pack_type': 'выбор типа пака', 'generating': 'создание пака', 'delivered': 'файлы готовы'}
GRADIENT_NAMES = ['Белый → голубой', 'Светло-голубой → синий', 'Белый → розовый', 'Золотой → оранжевый', 'Жёлтый → красный', 'Мятный → зелёный', 'Сиреневый → фиолетовый', 'Белый → серый', 'Без градиента']
COLOR_NAMES = ['Оригинальные', 'Синий', 'Голубой', 'Розовый', 'Фиолетовый', 'Золотой', 'Зелёный', 'Оранжевый', 'Серый']

def stage_name(stage):
    return STAGES.get(stage, {'CLOSED': 'завершён', 'REFUNDED': 'возврат', 'CANCELLED': 'отменён', 'refund_confirm': 'подтверждение отмены', 'refund_requested': 'проверка отмены', 'wallet_use_confirm': 'подтверждение использования бонусов'}.get(stage, 'редактирование' if stage.startswith('editor_') or stage == 'edit_menu' else 'данные сохранены'))

def collections(cat, o):
    return '💙【 Выберите коллекцию 】\n\n' + '\n'.join((f'{i}. {NAMES[c]}' for i, c in enumerate(cat.collections(), 1))) + f"\n\nВыбрано: {len(o['data']['cart'])}/{o['qty']}. Можно смешивать коллекции.\nВведите номер коллекции."

def cart(cat, o):
    return f"💙【 Ваш набор · {len(o['data']['cart'])}/{o['qty']} 】\n\n" + '\n'.join((f'{i}. {cat.label(c, n)}' for i, (c, n) in enumerate(o['data']['cart'], 1)))

def preview(o):
    from .textflow import summary
    label = 'Тексты: ' + summary(o['data']) if o['data'].get('individual_texts') else 'Текст 1: ' + o['data']['nick'] + ('\nТекст 2: ' + o['data']['text2'] if o['data'].get('text2') else '')
    return '💙【 Предпросмотр 】\n\n' + label + f"\nЭмодзи: {o['qty']} шт.\n\n!редактировать — оформление\n!назначить — распределение текстов\n!откат — отменить изменение\n\nСоздать пак: да / нет\nПосле подтверждения сборки изменение результата завершится."
