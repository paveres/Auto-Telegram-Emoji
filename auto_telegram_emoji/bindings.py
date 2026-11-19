__author__ = '@paveres'
__channel__ = 'https://t.me/g_plugins'
__contact__ = 'https://t.me/paveres'
import re
from decimal import Decimal, InvalidOperation

def validate(config):
    seen = set()
    for key, lot in config.get('lots', {}).items():
        marker = lot.get('marker', '')
        if not re.fullmatch('![a-z][a-z0-9_]{2,47}', marker) or marker in seen:
            raise ValueError('Метки должны быть уникальными: !gemoji_15')
        seen.add(marker)
        if type(lot.get('pack_size')) is not int or not 1 <= lot['pack_size'] <= 200:
            raise ValueError('Размер набора: 1–200')
        try:
            price = Decimal(str(lot['seller_price_rub']))
        except (KeyError, InvalidOperation):
            raise ValueError('Укажите цену продавца') from None
        if not price.is_finite() or price <= 0:
            raise ValueError('Цена должна быть положительной')
    return config

def match_order(order, config):
    lines = [line.strip() for line in (order.full_description or '').splitlines() if line.strip()]
    if not lines:
        return []
    result = []
    for key, lot in config.get('lots', {}).items():
        if lines[-1] != lot['marker'] or lines.count(lot['marker']) != 1:
            continue
        if lot.get('node_id') and (not order.subcategory or order.subcategory.id != int(lot['node_id'])):
            continue
        result.append((key, lot))
    return result
