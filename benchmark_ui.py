import time
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from benchmark import technical, compare_assets, compare_portfolio
from services import ServiceError, context, ask_gemini
from core import quote_is_old


def chart(frame, percent=False):
    fig = go.Figure()
    for name in frame.columns:
        fig.add_trace(go.Scatter(x=frame.index, y=frame[name], name=name, mode='lines'))
    fig.update_layout(template='plotly_dark', height=380, hovermode='x unified',
                      paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                      margin=dict(l=0,r=10,t=20,b=0), legend=dict(orientation='h'),
                      yaxis_title='Доходность, %' if percent else 'Цена SPY, USD',
                      xaxis_rangeslider_visible=False)
    st.plotly_chart(fig, width='stretch')


def render_benchmark(load, mode, ticker, portfolio, gemini, model, budget, render_answer):
    with st.container(border=True):
        st.markdown('<div class="hero-eyebrow">ОРИЕНТИР РЫНКА США</div>', unsafe_allow_html=True)
        st.header('S&P 500 · через ETF SPY')
        st.write('SPY — фонд, отслеживающий S&P 500. Ниже цена доли фонда в долларах, а не значение самого индекса в пунктах.')
        st.link_button('О фонде · State Street', 'https://www.ssga.com/us/en/individual/etfs/spdr-sp-500-etf-trust-spy')
        period = st.radio('Период SPY', ['1 месяц', '3 месяца', '6 месяцев', '1 год'], index=1, horizontal=True, key='spy_period')
        count = {'1 месяц':21, '3 месяца':63, '6 месяцев':126, '1 год':250}[period]
        try:
            snap = load('SPY', 250)
        except ServiceError as e:
            st.warning('Блок SPY временно недоступен. ' + str(e))
            return
        bars = snap['bars'][-count:]
        ta, window = technical(snap['bars']), technical(bars)
        st.caption(('ДЕМО · синтетические цены · ' if mode == 'demo' else 'Alpaca IEX · ') +
                   'Последнее доступное дневное закрытие: ' + bars[-1]['t'][:10] + ' · кэш до 5 минут. Это не потоковая цена.')
        if mode != 'demo' and quote_is_old(bars[-1]['t']):
            st.warning('Данные SPY устарели: последнее закрытие старше 5 суток. Выводы могут быть неактуальны.')
        cols = st.columns(4)
        cols[0].metric('SPY · доля ETF', f"${ta['last']:,.2f}", f"{ta['change']:+.2f}% за сессию")
        cols[1].metric('За выбранный период', f"{window['period_return']:+.2f}%")
        cols[2].metric('Волатильность · годовая', f"{window['volatility']:.1f}%")
        cols[3].metric('Просадка за период', f"{window['drawdown']:.1f}%")
        frame = pd.DataFrame(snap['bars']).set_index('t')
        plotted = pd.DataFrame({'SPY':frame.c, 'Средняя 50':frame.c.rolling(50).mean(), 'Средняя 200':frame.c.rolling(200).mean()}).tail(count)
        chart(plotted)
        st.caption(f'Показано {len(bars)} торговых сессий. Расчёты по закрытиям, без дивидендов. Короткое окно может скрывать более глубокие прошлые просадки.')
        tabs = st.tabs(['Технический анализ', 'Новости и влияние', 'Сценарии и риски', 'Сравнение доходности'])
        with tabs[0]:
            sma50, sma200 = ta['sma50'], ta['sma200']
            trend = ('выше' if ta['last'] > sma50 else 'ниже') if sma50 else None
            st.write(f"Цена {'выше' if ta['last'] > ta['sma20'] else 'ниже'} средней за 20 сессий (${ta['sma20']:.2f}).")
            if trend:
                st.write(f'Средняя за 50 сессий: ${sma50:.2f}; цена {trend} неё.')
            if sma200:
                st.write(f"Средняя за 200 сессий: ${sma200:.2f}. Долгосрочный ориентир {'поддерживает рост' if ta['last'] > sma200 else 'указывает на слабость цены'}.")
            else:
                st.info('Для средней за 200 сессий пока недостаточно истории.')
            if ta['rsi'] is not None:
                st.write(f"RSI 14 (простые средние): {ta['rsi']:.1f}. Значения выше 70 / ниже 30 — признаки сильного движения, а не команда продавать / покупать.")
            st.write(f"Диапазон последних 20 сессий: ${ta['support']:.2f}–${ta['resistance']:.2f}. Это наблюдаемые минимум и максимум, без гарантии поддержки или сопротивления.")
        with tabs[1]:
            st.caption('Заголовки по тикеру SPY могут не охватывать все события S&P 500. Полные статьи ИИ не читает.')
            if snap['news_error']:
                st.warning(snap['news_error'])
            if not snap['news']:
                st.info('Проверяемых свежих заголовков нет. Анализ текущего новостного фона недоступен.')
            for item in snap['news']:
                st.text(item['title'])
                st.caption(item['source'] + ' · ' + item['published'][:16])
                st.link_button('Источник', item['url'])
            st.write('Что проверять в публикациях: ставки и инфляция влияют на стоимость капитала; прибыль крупнейших компаний — на ожидания роста; геополитика — на неопределённость. Это рамка анализа, а не утверждение о сегодняшних событиях.')
            consent = st.checkbox('Разрешаю передать публичные заголовки и цены SPY в Gemini', key='spy_consent')
            if st.button('Проанализировать новости SPY с ИИ', disabled=not(gemini and mode == 'market' and snap['news'] and consent)):
                try:
                    if time.monotonic() - st.session_state.last_ai < 15:
                        raise ServiceError('Подождите 15 секунд между запросами.')
                    st.session_state.last_ai = time.monotonic()
                    ctx = context(snap)
                    answer = ask_gemini(ctx, 'Проанализируй только переданные заголовки SPY: возможное влияние на рынок, противоречия, риски и условия отмены гипотез. Не делай вид, что прочитал статьи. Каждый вывод свяжи с источником новости.', [], gemini, model, budget())
                    st.session_state['spy_analysis'] = (snap['bars'][-1]['t'], answer, ctx)
                except ServiceError as e:
                    st.warning(str(e))
            saved = st.session_state.get('spy_analysis')
            if saved and mode == 'market':
                st.caption('Разбор сохранённого снимка: ' + saved[0][:10] + '. Дата публикаций и полный контекст — в источниках ниже.')
                render_answer(saved[1], saved[2])
        with tabs[2]:
            st.write('Условные сценарии на следующие 20 торговых сессий. Это правила наблюдения, не прогноз цены или вероятности.')
            st.dataframe(pd.DataFrame([
                {'Сценарий':'Рост', 'Условие':f"Закрытия выше ${ta['resistance']:.2f}", 'Что проверять':'Сохранение пробоя; возврат в диапазон отменяет гипотезу.'},
                {'Сценарий':'Диапазон', 'Условие':f"Между ${ta['support']:.2f} и ${ta['resistance']:.2f}", 'Что проверять':'Выход из диапазона отменяет боковой сценарий.'},
                {'Сценарий':'Снижение', 'Условие':f"Закрытия ниже ${ta['support']:.2f}", 'Что проверять':'Возврат выше нижней границы ослабляет гипотезу.'}
            ]), hide_index=True, width='stretch')
            st.write(f"За выбранное окно волатильность составила {window['volatility']:.1f}% годовых, максимальная просадка {window['drawdown']:.1f}%. Эти оценки описывают прошлое и не ограничивают будущие потери.")
            st.write('Риски: концентрация индекса в крупнейших компаниях, переоценка ожиданий прибыли, рост ставок, резкие ценовые разрывы. SPY также имеет расходы фонда и отклонение от индекса. IEX отражает лишь часть рынка; дивиденды в расчёты не входят.')
            st.caption(f"Стресс-примеры без вероятностей: −10% от последнего закрытия → ${ta['last']*.9:.2f}; −20% → ${ta['last']*.8:.2f}.")
        with tabs[3]:
            selected = st.multiselect('Акции для сравнения', list(dict.fromkeys([ticker,'AAPL','MSFT','NVDA','TSLA','AMZN','GOOGL'])), default=[ticker], max_selections=5)
            try:
                histories = {'SPY · ETF':bars}
                for sym in selected:
                    if sym != 'SPY':
                        histories[sym] = load(sym, 250)['bars'][-count:]
                returns = compare_assets(histories)
                chart(returns, True)
                st.caption(f'Общие торговые даты: {returns.index[0]} — {returns.index[-1]}. Каждая серия начинается с 0%; ценовая доходность без дивидендов и комиссий.')
                last = returns.iloc[-1]
                st.dataframe(pd.DataFrame({'Доходность, %':last, 'Разница со SPY, п.п.':last-last['SPY · ETF']}), width='stretch')
            except (ServiceError, ValueError) as e:
                st.warning(str(e))
            st.markdown('**Виртуальный портфель против SPY**')
            st.caption('Симуляция по датам цен исполнения из истории операций, включая свободные деньги. SPY: условная покупка на весь стартовый капитал в первую дату. Это не подтверждённая история реальных вложений; выбранный выше период к этой истории не применяется. Сплиты уже учтены в ценах; старые количества в портфеле автоматически не пересчитываются.')
            if st.button('Рассчитать сравнение портфеля', key='portfolio_benchmark'):
                try:
                    syms = {t['symbol'] for t in portfolio['trades']}
                    if len(syms) > 20:
                        raise ValueError('Для одного сравнения поддерживается до 20 тикеров в истории.')
                    histories = {sym:load(sym, 250)['bars'] for sym in syms}
                    result = compare_portfolio(portfolio, histories, snap['bars'])
                    chart(result, True)
                    a,b = st.columns(2)
                    a.metric('Портфель · с первой операции', f"{result['Портфель'].iloc[-1]:+.2f}%")
                    b.metric('Разница со SPY', f"{result['Портфель'].iloc[-1]-result['SPY · ETF'].iloc[-1]:+.2f} п.п.")
                    st.caption(f'{result.index[0]} — {result.index[-1]}. Доступно {len(result)} сессий; один день ещё не показывает динамику.')
                except (ServiceError, ValueError, KeyError) as e:
                    st.warning(str(e) if not isinstance(e, KeyError) else 'Не хватает истории одного из тикеров.')
