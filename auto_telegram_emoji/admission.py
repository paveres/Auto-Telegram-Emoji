__author__ = '@justmeth'
__channel__ = 'https://t.me/g_plugins'
__contact__ = 'https://t.me/justmeth'
from .aliases import ALIASES

def accepts(order, text, catalog=None):
    stage = order['stage']
    head = text.split(maxsplit=1)[0] if text else ''
    if head.startswith('!'):
        return head in ALIASES
    if stage == 'pack_type':
        return text in {'1', '2', '-', '−'}
    if stage == 'selection_action':
        return text in {'1', '2'}
    if stage == 'text_pick':
        return text in {'+', '-', '−'} or (text.isdigit() and 1 <= int(text) <= len(order['data']['cart']))
    if stage in {'confirm', 'preview', 'style_confirm', 'refund_confirm', 'wallet_use_confirm'}:
        return text in {'+', '-', '−'}
    if stage == 'collection':
        return text.isdigit() and 1 <= int(text) <= len(catalog.collections())
    if stage == 'select':
        from .parser import numbers
        try:
            numbers(text, len(catalog.items(order['data']['collection'])))
            return True
        except ValueError:
            return False
    if stage in {'intro_pending', 'catalog_pending', 'generating', 'delivered', 'REVIEW', 'refund_requested'}:
        return False
    if stage == 'edit_menu':
        return text.isdigit() and 1 <= int(text) <= 9
    if stage in {'color', 'gradient'}:
        return text.isdigit()
    return True
