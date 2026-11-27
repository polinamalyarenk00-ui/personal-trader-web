"""Benchmark analytics. No private portfolio data is cached or sent to AI."""
from datetime import datetime
import math
import pandas as pd
from core import metrics


def prices(bars):
    series = pd.Series({b['t'][:10]: float(b['c']) for b in bars}, dtype=float).sort_index()
    if series.empty or not all(math.isfinite(x) and x > 0 for x in series):
        raise ValueError('Недостаточно корректных цен для сравнения.')
    return series


def technical(bars):
    s = prices(bars)
    m = metrics(bars)
    delta = s.diff().dropna().tail(14)
    gain, loss = delta.clip(lower=0).mean(), -delta.clip(upper=0).mean()
    rsi = 50 if gain == loss == 0 else 100 if loss == 0 else 100 - 100 / (1 + gain / loss)
    return dict(m, sma50=float(s.tail(50).mean()) if len(s) >= 50 else None,
                sma200=float(s.tail(200).mean()) if len(s) >= 200 else None,
                rsi=float(rsi) if len(delta) == 14 else None,
                support=min(float(b['l']) for b in bars[-20:]),
                resistance=max(float(b['h']) for b in bars[-20:]))


def compare_assets(histories):
    frame = pd.concat({name: prices(bars) for name, bars in histories.items()}, axis=1).dropna()
    if len(frame) < 2:
        raise ValueError('Нет двух общих торговых дат для сравнения.')
    return (frame / frame.iloc[0] - 1) * 100


def compare_portfolio(portfolio, histories, benchmark):
    trades = portfolio['trades']
    if not trades:
        raise ValueError('Добавьте виртуальную операцию: сравнение начнётся с даты первой цены исполнения.')
    dates = [t['timestamp'][:10] for t in trades]
    if dates != sorted(dates):
        raise ValueError('Даты цен операций идут не по порядку. Историческое сравнение недоступно для этой истории.')
    spy = prices(benchmark)
    series = {sym: prices(histories[sym]) for sym in {t['symbol'] for t in trades}}
    if dates[0] < spy.index[0] or dates[0] > spy.index[-1] or dates[-1] > spy.index[-1]:
        raise ValueError('История операций выходит за доступное окно SPY. Сравнение не рассчитано.')
    if any(d not in spy.index for d in dates):
        raise ValueError('Для даты операции нет закрытия SPY. Сравнение не рассчитано.')
    cash, holdings, cursor, rows = float(portfolio['initial']), {}, 0, []
    for day, spy_price in spy.loc[dates[0]:].items():
        while cursor < len(trades) and dates[cursor] == day:
            t = trades[cursor]
            qty = float(t['qty']) * (1 if t['side'] == 'buy' else -1)
            cash -= qty * float(t['price'])
            holdings[t['symbol']] = holdings.get(t['symbol'], 0) + qty
            cursor += 1
        active = {sym: qty for sym, qty in holdings.items() if abs(qty) > 1e-9}
        if any(day not in series[sym].index for sym in active):
            raise ValueError('Нет цены одной из позиций на общей торговой дате. Неполная оценка портфеля не показывается.')
        equity = cash + sum(qty * series[sym].loc[day] for sym, qty in active.items())
        rows.append((day, (equity / float(portfolio['initial']) - 1) * 100,
                     (spy_price / spy.loc[dates[0]] - 1) * 100))
    return pd.DataFrame(rows, columns=['Дата', 'Портфель', 'SPY · ETF']).set_index('Дата')
