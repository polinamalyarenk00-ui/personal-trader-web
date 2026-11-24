"""Pure portfolio and risk logic. No network, credentials or shared user state."""
import copy
import json
import math
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from statistics import stdev

SYMBOL = re.compile(r"^[A-Z][A-Z0-9.-]{0,9}$")


def symbol(value):
    value = str(value).strip().upper()
    if not SYMBOL.fullmatch(value):
        raise ValueError("Тикер: 1–10 латинских букв, цифр, точка или дефис.")
    return value


def number(value, maximum=Decimal('1000000000')):
    if isinstance(value, bool) or len(str(value)) > 64:
        raise ValueError("Некорректное число.")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError("Некорректное число.") from None
    if not result.is_finite() or result <= 0 or result > maximum or result.as_tuple().exponent < -8:
        raise ValueError("Число должно быть положительным и в допустимых пределах.")
    return result


def new_portfolio(mode):
    if mode not in ('demo', 'market'):
        raise ValueError("Неизвестный режим портфеля.")
    return {'version': 1, 'mode': mode, 'initial': '10000', 'cash': '10000',
            'positions': {}, 'trades': [], 'realized': '0'}


def trade(portfolio, ticker, side, quantity, price, timestamp, source):
    """Return a new ledger atomically; only virtual fills, no broker API."""
    ticker = symbol(ticker)
    qty, px = number(quantity, Decimal('1000000')), number(price)
    if side not in ('buy', 'sell') or len(portfolio['trades']) >= 1000:
        raise ValueError("Недопустимая операция или достигнут лимит 1000 операций.")
    if qty.as_tuple().exponent < -6:
        raise ValueError("Не более 6 знаков после запятой для количества.")
    try:
        if datetime.fromisoformat(timestamp.replace('Z', '+00:00')).tzinfo is None:
            raise ValueError()
    except (ValueError, AttributeError):
        raise ValueError("Нужна дата котировки с часовым поясом.") from None
    if not isinstance(source, str) or not source or len(source) > 200:
        raise ValueError("Не указан источник цены.")
    p = copy.deepcopy(portfolio)
    cash = Decimal(p['cash'])
    old = p['positions'].get(ticker, {'qty': '0', 'cost': '0'})
    held, cost = Decimal(old['qty']), Decimal(old['cost'])
    total = qty * px
    if side == 'buy':
        if total > cash:
            raise ValueError("Недостаточно виртуальных средств.")
        held, cost, cash = held + qty, cost + total, cash - total
    else:
        if qty > held:
            raise ValueError("Нельзя продать больше акций, чем есть в портфеле.")
        removed = cost * qty / held
        p['realized'] = str(Decimal(p['realized']) + total - removed)
        held, cost, cash = held - qty, cost - removed, cash + total
    if held:
        p['positions'][ticker] = {'qty': str(held), 'cost': str(cost)}
    else:
        p['positions'].pop(ticker, None)
    p['cash'] = str(cash)
    p['trades'].append({'symbol': ticker, 'side': side, 'qty': str(qty), 'price': str(px),
                        'timestamp': timestamp, 'source': source})
    return p


def export_portfolio(p):
    # Only the replayable ledger is exported, never chat, identity or secrets.
    return json.dumps({k: p[k] for k in ('version', 'mode', 'trades')}, ensure_ascii=False, indent=2)


def import_portfolio(raw, mode):
    if len(raw) > 512_000:
        raise ValueError("Файл слишком большой: максимум 500 КБ.")
    try:
        data = json.loads(raw)
        if data['version'] != 1 or data['mode'] != mode or not isinstance(data['trades'], list):
            raise ValueError()
        if len(data['trades']) > 1000:
            raise ValueError()
        result = new_portfolio(mode)
        for item in data['trades']:
            result = trade(result, item['symbol'], item['side'], item['qty'], item['price'],
                           item['timestamp'], item['source'])
        return result
    except (KeyError, TypeError, ValueError, OverflowError, RecursionError):
        raise ValueError("Файл повреждён, операции недопустимы или выбран другой режим.") from None


def metrics(bars):
    closes = [float(b['c']) for b in bars]
    if len(closes) < 3 or any(not math.isfinite(c) or c <= 0 for c in closes):
        raise ValueError("Для расчёта нужны минимум три корректные дневные свечи.")
    returns = [b / a - 1 for a, b in zip(closes, closes[1:])]
    peak, drawdown = closes[0], 0.0
    for c in closes:
        peak = max(peak, c)
        drawdown = min(drawdown, c / peak - 1)
    return {'last': closes[-1], 'change': (closes[-1] / closes[-2] - 1) * 100,
            'period_return': (closes[-1] / closes[0] - 1) * 100,
            'volatility': stdev(returns) * math.sqrt(252) * 100,
            'drawdown': drawdown * 100,
            'sma20': sum(closes[-20:]) / len(closes[-20:]), 'observations': len(closes)}


def quote_is_old(timestamp, now=None):
    now = now or datetime.now(timezone.utc)
    try:
        age = (now - datetime.fromisoformat(timestamp.replace('Z', '+00:00'))).total_seconds()
        return age > 5 * 86400 or age < -300
    except (ValueError, TypeError):
        return True
