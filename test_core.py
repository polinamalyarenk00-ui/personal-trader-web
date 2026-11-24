import json
from decimal import Decimal
import pytest
from core import *
from services import demo_market

T = '2025-12-31T00:00:00+00:00'

def test_buy_sell_accounting_and_atomicity():
    p = new_portfolio('demo')
    q = trade(p, 'AAPL', 'buy', '2', '100', T, 'DEMO')
    assert p['cash'] == '10000' and not p['positions']
    q = trade(q, 'AAPL', 'sell', '1', '120', T, 'DEMO')
    assert Decimal(q['cash']) == 9920
    assert Decimal(q['realized']) == 20
    assert q['positions']['AAPL'] == {'qty': '1', 'cost': '100'}

@pytest.mark.parametrize('qty', ['NaN', 'Infinity', '-1', '0', '1e100', True, '0.1234567', '1e-7', '1e-999999999'])
def test_bad_quantities(qty):
    with pytest.raises(ValueError):
        trade(new_portfolio('demo'), 'AAPL', 'buy', qty, 100, T, 'DEMO')

def test_no_leverage_or_short():
    p = new_portfolio('demo')
    for side, qty in [('buy', 101), ('sell', 1)]:
        with pytest.raises(ValueError):
            trade(p, 'AAPL', side, qty, 100, T, 'DEMO')
    assert p == new_portfolio('demo')

def test_export_replay_and_separation():
    p = trade(new_portfolio('demo'), 'AAPL', 'buy', '.125', '123.45', T, 'DEMO')
    assert import_portfolio(export_portfolio(p), 'demo') == p
    with pytest.raises(ValueError):
        import_portfolio(export_portfolio(p), 'market')
    data = json.loads(export_portfolio(p))
    data['cash'] = '999999'
    assert import_portfolio(json.dumps(data), 'demo')['cash'] == p['cash']

@pytest.mark.parametrize('raw', ['[]', 'null', '{', '{"version":1,"mode":"demo","trades":[{}]}', 'x' * 512001])
def test_bad_import(raw):
    with pytest.raises(ValueError):
        import_portfolio(raw, 'demo')

def test_metrics_known_path():
    result = metrics([{'c': c} for c in (100, 120, 90, 110)])
    assert result['drawdown'] == -25
    assert result['period_return'] == pytest.approx(10)
    assert result['sma20'] == 105

def test_sessions_independent():
    a, b = new_portfolio('demo'), new_portfolio('demo')
    a = trade(a, 'AAPL', 'buy', 1, 100, T, 'DEMO')
    assert not b['positions'] and b['cash'] == '10000'

def test_demo_deterministic_and_explicit():
    a, b = demo_market('AAPL'), demo_market('AAPL')
    assert a['bars'] == b['bars'] and a['mode'] == 'demo' and a['news'] == []
    assert all(v['l'] <= v['c'] <= v['h'] for v in a['bars'])

@pytest.mark.parametrize('ticker', ['../../x', 'AAPL?key=bad', '<script>', ''])
def test_symbol_validation(ticker):
    with pytest.raises(ValueError):
        symbol(ticker)

def test_stale_dates():
    assert quote_is_old(T, datetime(2026, 2, 1, tzinfo=timezone.utc))
    assert not quote_is_old(T, datetime(2026, 1, 2, tzinfo=timezone.utc))
