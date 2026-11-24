import json
from unittest.mock import Mock
import pytest
import requests
import services as s


def response(status, data):
    return Mock(status_code=status, json=Mock(return_value=data))

@pytest.mark.parametrize('status', [401, 403, 429, 404, 302])
def test_errors_do_not_leak_secrets(monkeypatch, status):
    call = Mock(return_value=response(status, {'error': 'SECRET-VALUE'}))
    monkeypatch.setattr(s.requests, 'request', call)
    with pytest.raises(s.ServiceError) as exc:
        s.request_json('GET', 'https://data.alpaca.markets/v2/stocks/bars', {})
    assert 'SECRET-VALUE' not in str(exc.value)
    assert call.call_count == 1

def test_network_error_safe(monkeypatch):
    monkeypatch.setattr(s.requests, 'request', Mock(side_effect=requests.Timeout('SECRET-VALUE')))
    with pytest.raises(s.ServiceError) as exc:
        s.request_json('GET', 'https://example.com', {})
    assert 'SECRET-VALUE' not in str(exc.value)

def test_retry_read_only(monkeypatch):
    call = Mock(side_effect=[response(503, {}), response(200, {'ok': True})])
    monkeypatch.setattr(s.requests, 'request', call)
    monkeypatch.setattr(s.time, 'sleep', lambda _: None)
    assert s.request_json('GET', 'https://example.com', {}) == {'ok': True}
    assert call.call_count == 2
    call.reset_mock(side_effect=True)
    call.return_value = response(503, {})
    with pytest.raises(s.ServiceError):
        s.request_json('POST', 'https://example.com', {})
    assert call.call_count == 1

def test_bad_json(monkeypatch):
    monkeypatch.setattr(s.requests, 'request', Mock(return_value=Mock(status_code=200, json=Mock(side_effect=ValueError))))
    with pytest.raises(s.ServiceError):
        s.request_json('GET', 'https://example.com', {})

def test_budget():
    b = s.Budget(minute=1, day=2)
    b.acquire(100)
    with pytest.raises(s.ServiceError): b.acquire(110)
    b.acquire(161)
    with pytest.raises(s.ServiceError): b.acquire(250)
    b.acquire(86500)

@pytest.mark.parametrize('url', ['javascript:alert(1)', 'http://bad.com', 'https://user:pass@example.com', None, 'https://[broken'])
def test_url_guard(url):
    assert not s.safe_url(url)

def test_sources_and_gemini_payload(monkeypatch):
    ctx = s.context(s.demo_market('AAPL'))
    answer = s.demo_answer(ctx)
    call = Mock(return_value={'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text': json.dumps(answer)}]}}]})
    monkeypatch.setattr(s, 'request_json', call)
    result = s.ask_gemini(ctx, 'Риски?', [], 'TOPSECRET', 'gemini-3.1-flash-lite', s.Budget())
    assert result == answer
    args, kw = call.call_args
    assert 'TOPSECRET' not in args[1] and 'TOPSECRET' not in json.dumps(kw['payload'])
    assert args[2]['x-goog-api-key'] == 'TOPSECRET'
    answer['ideas'][0]['source_ids'] = ['N999']
    with pytest.raises(ValueError): s.validate_answer(answer, ctx)

def test_market_pagination_and_news_failure(monkeypatch):
    bars = s.demo_market('AAPL')['bars'][:6]
    call = Mock(side_effect=[{'bars': {'AAPL': bars[:3]}, 'next_page_token': 'next'},
                            {'bars': {'AAPL': bars[3:]}}, s.ServiceError('Новости недоступны')])
    monkeypatch.setattr(s, 'request_json', call)
    result = s.market('AAPL', 30, 'key', 'secret')
    assert len(result['bars']) == 6 and result['mode'] == 'market'
    assert result['news_error'] == 'Новости недоступны'
    assert call.call_args_list[0].kwargs['params']['feed'] == 'iex'
    assert all('data.alpaca.markets' in c.args[1] for c in call.call_args_list)

def test_empty_market_does_not_fallback(monkeypatch):
    monkeypatch.setattr(s, 'request_json', Mock(return_value={'bars': {}}))
    with pytest.raises(s.ServiceError): s.market('AAPL', 30, 'key', 'secret')


def test_placeholder_key_rejected_without_network(monkeypatch):
    call = Mock()
    monkeypatch.setattr(s.requests, 'request', call)
    with pytest.raises(s.ServiceError) as error:
        s.request_json('GET', 'https://data.alpaca.markets/v2/stocks/bars', {'APCA-API-KEY-ID': 'ваш ключ'})
    assert 'ALPACA_API_KEY' in str(error.value)
    call.assert_not_called()
