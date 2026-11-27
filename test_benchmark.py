import pytest
from benchmark import compare_assets, compare_portfolio, technical
from core import new_portfolio, trade
from services import demo_market


def bars(values, start=1):
    return [{'t':f'2026-01-{i:02d}T00:00:00Z','c':v,'h':v+1,'l':v-1,'o':v} for i,v in enumerate(values,start)]


def test_common_dates_and_same_baseline():
    result = compare_assets({'SPY':bars([100,110,121]), 'AAPL':bars([200,220],2)})
    assert len(result) == 2
    assert result.iloc[0].tolist() == [0,0]
    assert result.iloc[-1].tolist() == pytest.approx([10,10])


def test_portfolio_cash_and_sale():
    p = new_portfolio('demo')
    p = trade(p,'AAPL','buy',10,100,'2026-01-01T00:00:00Z','test')
    p = trade(p,'AAPL','sell',5,110,'2026-01-02T00:00:00Z','test')
    result = compare_portfolio(p, {'AAPL':bars([100,110,120])}, bars([100,105,110]))
    assert result['Портфель'].tolist() == pytest.approx([0,1,1.5])
    assert result['SPY · ETF'].tolist() == pytest.approx([0,5,10])


def test_missing_position_price_rejected():
    p = trade(new_portfolio('demo'),'AAPL','buy',1,100,'2026-01-01T00:00:00Z','test')
    with pytest.raises(ValueError,match='Нет цены'):
        compare_portfolio(p, {'AAPL':bars([100,110])}, bars([100,105,110]))


def test_old_history_rejected():
    p = trade(new_portfolio('demo'),'AAPL','buy',1,100,'2025-01-01T00:00:00Z','test')
    with pytest.raises(ValueError,match='окно'):
        compare_portfolio(p, {'AAPL':bars([100,110])}, bars([100,105,110]))


def test_empty_portfolio():
    with pytest.raises(ValueError,match='Добавьте'):
        compare_portfolio(new_portfolio('demo'), {}, bars([100,110]))


def test_technical_no_false_200_day_average():
    result = technical(bars(list(range(100,130))))
    assert result['sma200'] is None
    assert result['sma50'] is None
    assert result['rsi'] == 100
    result = technical(demo_market('SPY',250)['bars'])
    assert result['sma200'] is not None
    assert 0 <= result['rsi'] <= 100


def test_nonchronological_trades_rejected():
    p = trade(new_portfolio('demo'),'AAPL','buy',1,100,'2026-01-02T00:00:00Z','test')
    p = trade(p,'AAPL','buy',1,100,'2026-01-01T00:00:00Z','test')
    with pytest.raises(ValueError,match='порядку'):
        compare_portfolio(p, {'AAPL':bars([100,110])}, bars([100,105,110]))


def test_home_period_and_portfolio_empty_state():
    from pathlib import Path
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_file(str(Path(__file__).with_name('app.py'))).run()
    assert not app.exception
    assert any('S&P 500' in x.value for x in app.header)
    app.radio(key='spy_period').set_value('1 год').run()
    assert not app.exception
    app.button(key='portfolio_benchmark').click().run()
    assert not app.exception
    assert any('Добавьте виртуальную' in x.value for x in app.warning)
