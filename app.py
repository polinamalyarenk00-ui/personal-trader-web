import os
import time
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from benchmark_ui import render_benchmark
from core import (symbol, metrics, new_portfolio, trade, export_portfolio,
                         import_portfolio, quote_is_old)
from services import (ServiceError, Budget, demo_market, market, context,
                             demo_answer, ask_gemini)

st.set_page_config(page_title='Личный трейдер Web 1.0', page_icon='◈', layout='wide')
st.markdown('''<style>
.stApp {background: radial-gradient(ellipse at 80% 0%, #14263a 0%, #0b1019 45%); color:#e8eef5;}
.block-container {padding-top:4.5rem; max-width:1500px; padding-bottom:3rem;}
[data-testid="stSidebar"] {background:#0b121d; border-right:1px solid #243147;}
h1 {font-weight:700!important; letter-spacing:-.055em!important; font-size:2.8rem!important;}
h2,h3 {letter-spacing:-.025em;}
[data-testid="stMetric"] {background:linear-gradient(135deg,#172333,#101925);border:1px solid #29384a;border-radius:16px;padding:18px;}
[data-testid="stMetricLabel"] {color:#a4b4c8;}
[data-testid="stMetricValue"] {font-size:1.85rem;}
[data-testid="stVerticalBlockBorderWrapper"] {border-radius:16px;}
.stButton>button {border-radius:10px;min-height:42px;}
.hero-eyebrow {color:#72dcc2;font-size:.85rem;letter-spacing:.17em;font-weight:600;}
.subtitle {color:#a5b4c6;font-size:1.05rem;max-width:760px;line-height:1.6;}
.brand {font-size:1.35rem;font-weight:700;padding:8px 0 22px;}
.caption {color:#a5b4c6;font-size:.9rem;}
@media(max-width:640px){h1{font-size:2rem!important;}.block-container{padding-top:4rem;}}
</style>''', unsafe_allow_html=True)


def secret(name, default=''):
    value = os.environ.get(name)
    if value is not None:
        return value
    try:
        return str(st.secrets.get(name, default))
    except (FileNotFoundError, st.errors.StreamlitSecretNotFoundError):
        return default


@st.cache_resource
def ai_budget():
    return Budget(minute=4, day=100)


@st.cache_resource
def market_budget():
    return Budget(minute=90, day=6000)


@st.cache_data(ttl=300, max_entries=100, show_spinner=False)
def load_market(ticker, days, key, api_secret):
    market_budget().acquire()
    return market(ticker, days, key, api_secret)


def render_answer(answer, ctx):
    st.text(answer['summary'])
    for name, label in [('ideas', 'Идеи для исследования'), ('risks', 'Что может пойти не так')]:
        st.markdown('**' + label + '**')
        for item in answer[name]:
            st.text(item['text'])
            st.caption('Опора на данные: ' + ', '.join(item['source_ids']))
    st.caption('Ограничения: ' + answer['missing'])
    with st.expander('Источники и снимок данных этого ответа'):
        for source in ctx['sources']:
            st.text(source['id'] + ' · ' + source.get('title', '') + ' · ' + source.get('as_of', source.get('published', '')))
            if source.get('url'):
                st.link_button('Открыть источник ' + source['id'], source['url'])
        st.json(ctx, expanded=False)
    st.caption('Наличие ссылки подтверждает происхождение контекста, но не гарантирует правильность вывода ИИ.')


key, api_secret, gemini = secret('ALPACA_API_KEY'), secret('ALPACA_SECRET_KEY'), secret('GEMINI_API_KEY')
model = secret('GEMINI_MODEL', 'gemini-3.1-flash-lite')
with st.sidebar:
    st.markdown('<div class="brand">◈ Личный трейдер</div>', unsafe_allow_html=True)
    page = st.radio('Рабочее пространство', ['Обзор рынка', 'Чат с ИИ', 'Идеи и риски', 'Виртуальный портфель', 'Подключение'], label_visibility='collapsed')
    st.divider()
    mode_label = st.selectbox('Источник данных', ['Демо · без ключей', 'Рынок · Alpaca IEX'])
    mode = 'demo' if mode_label.startswith('Демо') else 'market'
    ticker_input = st.text_input('Тикер акции или ETF', 'AAPL', max_chars=10, help='Например: AAPL, MSFT, NVDA, SPY, TSLA.')
    days = st.select_slider('Дневных свечей', options=[30, 90, 180, 250], value=90)
    st.caption('США · USD · без автоматических сделок')
    st.divider()
    if mode == 'demo':
        st.info('ДЕМО: цены синтетические. Реальные новости не загружаются.')
    else:
        st.caption('IEX — часть рынка США. Дневные данные до конца предыдущих суток UTC. Кэш: 5 минут.')
    st.caption('Портфель и переписка доступны только в этой сессии. Перед закрытием сохраните портфель в файл.')

st.markdown('<div class="hero-eyebrow">ВАШЕ ПРОСТРАНСТВО ДЛЯ РЕШЕНИЙ</div>', unsafe_allow_html=True)
st.title('Личный трейдер Web 1.0')
st.markdown('<p class="subtitle">Рынок в контексте. Идеи с аргументами. Риск под контролем.<br>Изучайте инвестиции и проверяйте гипотезы на виртуальном капитале.</p>', unsafe_allow_html=True)
st.caption('Образовательный инструмент. Не индивидуальная инвестиционная рекомендация. Доходность не гарантируется.')

if page == 'Подключение':
    st.header('Начните без настройки')
    st.success('Деморежим работает без регистрации и ключей. Выберите любой раздел слева.')
    a, b, c = st.columns(3)
    a.metric('Демо', 'Готово')
    b.metric('Alpaca', 'Ключи заданы' if key and api_secret else 'Не подключён')
    c.metric('Gemini', 'Ключ задан' if gemini else 'Не подключён')
    st.caption('Наличие ключа не означает, что соединение уже проверено.')
    st.subheader('Для владельца приложения')
    st.write('Добавьте ключи только в Streamlit Cloud → App settings → Secrets. Не отправляйте их в чат и не загружайте на GitHub.')
    st.code('ALPACA_API_KEY = "ваш ключ"\nALPACA_SECRET_KEY = "ваш секрет"\nGEMINI_API_KEY = "ваш ключ"\nGEMINI_MODEL = "gemini-3.1-flash-lite"', language='toml')
    st.write('Бесплатность зависит от тарифов и доступности сервисов в вашем регионе. Не подключайте платный биллинг для бесплатного сценария. Приложение не может определить тариф по API-ключу.')
    st.link_button('Ключ Gemini в Google AI Studio', 'https://aistudio.google.com/api-keys')
    st.link_button('Alpaca · кабинет', 'https://app.alpaca.markets/')
    st.link_button('Доступные регионы Gemini', 'https://ai.google.dev/gemini-api/docs/available-regions')
    st.subheader('Приватность и сохранение')
    st.write('Без аккаунтов и общей базы: отдельный портфель и чат для каждой браузерной сессии. Обновление страницы, разрыв сессии или перезапуск сервера могут удалить их. Скачивайте резервную копию. Вкладки не синхронизируются.')
    st.write('В Gemini отправляются вопрос, последние сообщения этого диалога и показанный рыночный контекст. Портфель автоматически не отправляется. На бесплатном тарифе Google может использовать запросы для улучшения продуктов; не вводите личные или конфиденциальные сведения.')
    st.write('Локальные ограничения: до 4 запросов ИИ в минуту и 100 за 24 часа на процесс сервера. Это защита небольшой публичной демонстрации, а не распределённая система квот. Квоты провайдера могут быть ниже.')
    st.stop()

try:
    ticker = symbol(ticker_input)
except ValueError as e:
    st.warning(str(e))
    st.stop()

# Private data lives exclusively in session_state, never in cache or on server disk.
for name, value in [('portfolios', {}), ('chats', {}), ('last_ai', 0.0)]:
    if name not in st.session_state:
        st.session_state[name] = value
if mode not in st.session_state.portfolios:
    st.session_state.portfolios[mode] = new_portfolio(mode)

snapshot = None
if mode == 'market' and not (key and api_secret):
    st.warning('Alpaca не подключён. Выберите деморежим или добавьте ключи в настройки сервера. Выдуманные цены не подставляются.')
else:
    try:
        with st.spinner('Собираем рыночный контекст…'):
            snapshot = demo_market(ticker, days) if mode == 'demo' else load_market(ticker, days, key, api_secret)
    except ServiceError as e:
        st.warning(str(e))

if snapshot:
    m, ctx = metrics(snapshot['bars']), context(snapshot)
    st.caption(f"{'ДЕМО · СИНТЕТИЧЕСКИЕ ДАННЫЕ' if mode == 'demo' else 'ALPACA · IEX'}  |  {ticker}  |  Последняя свеча: {snapshot['bars'][-1]['t'][:10]}  |  Получено: {snapshot['fetched_at'][:19]} UTC")
    if mode == 'market' and quote_is_old(snapshot['bars'][-1]['t']):
        st.warning('Последняя свеча старше 5 суток или имеет некорректную дату. Виртуальные операции по ней отключены.')

if page == 'Обзор рынка':
    def benchmark_load(sym, length):
        if mode == 'market' and not (key and api_secret):
            raise ServiceError('Добавьте ключи Alpaca или выберите деморежим.')
        return demo_market(sym, length) if mode == 'demo' else load_market(sym, length, key, api_secret)
    render_benchmark(benchmark_load, mode, ticker, st.session_state.portfolios[mode], gemini, model, ai_budget, render_answer)
    st.divider()
    st.header('Компании · ' + ticker)
    if not snapshot:
        st.stop()
    columns = st.columns(4)
    columns[0].metric(f'{ticker} · закрытие', f"${m['last']:,.2f}", f"{m['change']:+.2f}% за сессию")
    columns[1].metric('Изменение за период', f"{m['period_return']:+.2f}%")
    columns[2].metric('Годовая волатильность', f"{m['volatility']:.1f}%")
    columns[3].metric('Максимальная просадка', f"{m['drawdown']:.1f}%")
    left, right = st.columns([2.3, 1], gap='large')
    with left:
        st.subheader('Динамика цены')
        kind = st.radio('Вид графика', ['Линия', 'Свечи'], horizontal=True, label_visibility='collapsed')
        frame = pd.DataFrame(snapshot['bars'])
        fig = go.Figure()
        if kind == 'Свечи':
            fig.add_trace(go.Candlestick(x=frame.t, open=frame.o, high=frame.h, low=frame.l, close=frame.c,
                                        increasing_line_color='#6ce0bf', decreasing_line_color='#f58a99', name=ticker))
        else:
            fig.add_trace(go.Scatter(x=frame.t, y=frame.c, mode='lines', line={'color': '#70dfc0', 'width': 2.5},
                                    fill='tozeroy', fillcolor='rgba(112,223,192,.07)', name='Закрытие'))
        fig.add_trace(go.Scatter(x=frame.t, y=frame.c.rolling(20).mean(), line={'color': '#829bfa', 'width': 1.5}, name='Средняя 20'))
        fig.update_layout(template='plotly_dark', height=420, margin=dict(l=0,r=10,t=10,b=0),
                          paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                          font=dict(color='#b8c7d9', size=14), legend=dict(orientation='h', y=1.12),
                          xaxis_rangeslider_visible=False, yaxis_title='USD', yaxis=dict(autorange=True, rangemode='normal'))
        st.plotly_chart(fig, width='stretch', config={'displayModeBar': False})
        st.caption('Расчёты по дневным закрытиям. Волатильность: стандартное отклонение дневной доходности × √252. Просадка: падение от предыдущего максимума в выбранном окне. Дивиденды не включены.')
        st.download_button('Скачать данные графика · CSV', frame.to_csv(index=False).encode(), file_name=f'{ticker}-{mode}.csv', mime='text/csv')
    with right:
        st.subheader('Лента источников')
        if snapshot['news_error']:
            st.warning(snapshot['news_error'])
        st.caption(snapshot['news_status'])
        if snapshot['news']:
            for news in snapshot['news']:
                with st.container(border=True):
                    st.text(news['title'])
                    st.caption(news['source'] + ' · ' + news['published'][:16])
                    st.link_button('Читать первоисточник', news['url'])
        else:
            st.info('Публикаций нет. Ниже — справочные ресурсы, не текущие новости.')
            st.link_button('SEC · отчётность компаний', 'https://www.sec.gov/edgar/search/')
            st.link_button('FRED · макроэкономика', 'https://fred.stlouisfed.org/')
    with st.expander('Проверяемый контекст · JSON'):
        st.json(ctx)

elif page in ('Чат с ИИ', 'Идеи и риски'):
    if not snapshot:
        st.stop()
    st.subheader('Разберём рынок вместе' if page == 'Чат с ИИ' else 'Сначала гипотеза. Затем проверка.')
    chat_key = mode + ':' + ticker
    history = st.session_state.chats.setdefault(chat_key, [])
    online = bool(gemini) and mode == 'market'
    consent = False
    if online:
        consent = st.checkbox('Разрешаю отправить мой вопрос и историю этого диалога в Gemini. Личные данные не ввожу.', key='consent')
    else:
        st.info('Демонстрационный помощник: ответы по шаблону без внешнего ИИ. Для диалога подключите Gemini и Alpaca и выберите «Рынок».')
    if page == 'Идеи и риски':
        render_answer(demo_answer(ctx), ctx)
        question = 'Сформулируй до трёх условных инвестиционных гипотез, риски и условия отмены на основе текущего контекста.' if st.button('Запросить разбор Gemini', disabled=not (online and consent), type='primary') else None
    else:
        for entry in history:
            with st.chat_message('user'):
                st.text(entry['question'])
            with st.chat_message('assistant'):
                render_answer(entry['answer'], entry['context'])
        question = st.chat_input('Например: что говорит динамика AAPL о риске?', max_chars=2000,
                                 disabled=online and not consent)
    if question:
        try:
            if online:
                if time.monotonic() - st.session_state.last_ai < 15:
                    raise ServiceError('Подождите 15 секунд между запросами.')
                st.session_state.last_ai = time.monotonic()
                with st.spinner('ИИ изучает снимок данных…'):
                    answer = ask_gemini(ctx, question, [{'question': h['question'], 'summary': h['answer']['summary']} for h in history], gemini, model, ai_budget())
            else:
                answer = demo_answer(ctx, question)
            history.append({'question': question, 'answer': answer, 'context': ctx})
            del history[:-12]
            if page == 'Чат с ИИ':
                st.rerun()
            with st.container(border=True):
                render_answer(answer, ctx)
        except ServiceError as e:
            st.warning(str(e))
    if st.button('Очистить диалог', disabled=not history):
        st.session_state.chats[chat_key] = []
        st.rerun()

elif page == 'Виртуальный портфель':
    p = st.session_state.portfolios[mode]
    st.subheader('Ваш учебный капитал')
    st.caption('Отдельные портфели для демо и рынка. Старт: $10 000. Нет плеча, шортов, комиссий и реальных сделок.')
    a, b, c = st.columns(3)
    a.metric('Свободные средства', f"${float(p['cash']):,.2f}")
    b.metric('Вложено · себестоимость', f"${sum(float(v['cost']) for v in p['positions'].values()):,.2f}")
    c.metric('Результат закрытых операций', f"${float(p['realized']):+,.2f}")
    if p['positions']:
        rows = []
        for sym, pos in p['positions'].items():
            current = m['last'] if snapshot and sym == ticker else None
            rows.append({'Тикер': sym, 'Количество': float(pos['qty']), 'Средняя цена, $': float(pos['cost']) / float(pos['qty']),
                         'Себестоимость, $': float(pos['cost']), 'Оценка по выбранной свече, $': current * float(pos['qty']) if current else None,
                         'Нереализованный результат, $': current * float(pos['qty']) - float(pos['cost']) if current else None})
        st.dataframe(pd.DataFrame(rows), hide_index=True, width='stretch')
        st.caption('Переоценка доступна для выбранного слева тикера. Пустые значения не означают ноль. Общая рыночная стоимость не рассчитывается по неполным ценам.')
        total_cost = sum(float(v['cost']) for v in p['positions'].values())
        largest = max(float(v['cost']) for v in p['positions'].values()) / (total_cost + float(p['cash'])) * 100
        st.info(f'Концентрация по себестоимости: крупнейшая позиция — {largest:.1f}% учтённого капитала. Это не рыночная оценка риска.')
    else:
        st.info('Пока нет позиций. Добавьте первую виртуальную покупку ниже.')
    with st.container(border=True):
        st.markdown('**Виртуальная операция**')
        if snapshot:
            st.write(f"{ticker} · цена симуляции ${m['last']:.2f} · свеча {snapshot['bars'][-1]['t'][:10]}")
            st.caption('Исполнение моделируется по последнему дневному закрытию, а не по текущей рыночной цене.')
            with st.form('virtual_trade'):
                side = st.selectbox('Действие', ['Купить виртуально', 'Продать виртуально'])
                qty = st.number_input('Количество акций', min_value=0.000001, max_value=1000000.0, value=1.0, format='%.6f')
                submitted = st.form_submit_button('Записать операцию', disabled=mode == 'market' and quote_is_old(snapshot['bars'][-1]['t']))
            if submitted:
                try:
                    st.session_state.portfolios[mode] = trade(p, ticker, 'buy' if side.startswith('Купить') else 'sell', qty,
                                                             m['last'], snapshot['bars'][-1]['t'], snapshot['source'])
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))
        else:
            st.info('Для операции нужны доступные котировки. Сохранение и восстановление портфеля доступны без них.')
    if p['trades']:
        with st.expander('История виртуальных операций'):
            df = pd.DataFrame(p['trades']).rename(columns={'symbol':'Тикер','side':'Операция','qty':'Количество','price':'Цена, $','timestamp':'Дата цены','source':'Источник'})
            df['Операция'] = df['Операция'].map({'buy':'Покупка','sell':'Продажа'})
            st.dataframe(df, hide_index=True, width='stretch')
    st.download_button('Сохранить портфель', export_portfolio(p), file_name=f'portfolio-{mode}.json', mime='application/json', type='primary')
    with st.expander('Восстановить портфель из файла'):
        st.caption('Импорт заменяет портфель этой сессии. Файл проверяется повторным исполнением истории; это личная копия, не заверенная выписка.')
        upload = st.file_uploader('Файл портфеля JSON · до 500 КБ', type=['json'])
        if st.button('Восстановить', disabled=upload is None):
            try:
                st.session_state.portfolios[mode] = import_portfolio(upload.getvalue(), mode)
                st.rerun()
            except ValueError as e:
                st.error(str(e))
    with st.expander('Начать заново'):
        confirm = st.checkbox('Удалить виртуальные операции этого режима в текущей сессии')
        if st.button('Сбросить до $10 000', disabled=not confirm):
            st.session_state.portfolios[mode] = new_portfolio(mode)
            st.rerun()
