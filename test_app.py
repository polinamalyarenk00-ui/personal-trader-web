from pathlib import Path
from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parent / 'app.py')

def app():
    return AppTest.from_file(APP, default_timeout=30).run()

def test_all_pages_without_keys():
    a = app()
    assert not a.exception
    for page in ['Чат с ИИ', 'Идеи и риски', 'Виртуальный портфель', 'Подключение', 'Обзор рынка']:
        a.sidebar.radio[0].set_value(page).run()
        assert not a.exception, page

def test_virtual_purchase_isolated_between_sessions():
    a = app()
    a.sidebar.radio[0].set_value('Виртуальный портфель').run()
    next(b for b in a.button if b.label == 'Записать операцию').click().run()
    assert not a.exception
    assert a.session_state['portfolios']['demo']['positions']['AAPL']['qty'] == '1.0'
    b = app()
    assert not b.session_state['portfolios']['demo']['positions']

def test_chat_demo_and_clear():
    a = app()
    a.sidebar.radio[0].set_value('Чат с ИИ').run()
    a.chat_input[0].set_value('Какие риски?').run()
    assert not a.exception
    assert len(a.session_state['chats']['demo:AAPL']) == 1
    next(b for b in a.button if b.label == 'Очистить диалог').click().run()
    assert not a.session_state['chats']['demo:AAPL']

def test_missing_keys_and_invalid_symbol():
    a = app()
    a.sidebar.selectbox[0].set_value('Рынок · Alpaca IEX').run()
    assert not a.exception and a.warning
    a.sidebar.text_input[0].set_value('../bad').run()
    assert not a.exception and a.warning
