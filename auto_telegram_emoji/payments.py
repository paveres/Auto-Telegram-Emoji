__author__ = '@justmeth'
__channel__ = 'https://t.me/g_plugins'
__contact__ = 'https://t.me/justmeth'
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation

def cents(value):
    try:
        amount = Decimal(str(value))
    except InvalidOperation:
        raise ValueError('Некорректная сумма заказа.') from None
    if not amount.is_finite() or amount < 0:
        raise ValueError('Некорректная сумма заказа.')
    return amount.quantize(Decimal('.01'), rounding=ROUND_HALF_UP)

def expected_total(unit_price, units):
    if isinstance(units, bool) or not isinstance(units, int) or units < 1:
        raise ValueError('Некорректное количество.')
    price = Decimal(str(unit_price))
    if not price.is_finite() or price <= 0:
        raise ValueError('Некорректная цена лота.')
    return cents(price * units)

def sufficient(paid, unit_price, units):
    return cents(paid) >= expected_total(unit_price, units)
