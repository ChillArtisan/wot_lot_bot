import httpx
import pytest

from wot_lot_bot.lolz import LolzClient, LolzError, parse_item_id


@pytest.mark.parametrize("text, expected", [
    ("https://lzt.market/123456789/", 123456789),
    ("https://lzt.market/123456789", 123456789),
    ("lzt.market/123456789/", 123456789),
    ("https://lolz.live/market/123456789/", 123456789),
    ("https://zelenka.guru/market/123456789/?ref=1", 123456789),
    ("глянь https://lzt.market/123456789/ плиз", 123456789),
    ("123456789", 123456789),
    ("  987654  ", 987654),
])
def test_parse_item_id(text, expected):
    assert parse_item_id(text) == expected


@pytest.mark.parametrize("text", [
    "", "привет", "https://example.com/123456789/", "12", "https://lzt.market/world-of-tanks/",
])
def test_parse_item_id_rejects(text):
    assert parse_item_id(text) is None


def _client(handler) -> LolzClient:
    return LolzClient("token", "https://api.test", transport=httpx.MockTransport(handler))


async def test_get_item_sends_bearer_and_returns_item():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers["Authorization"]
        seen["path"] = request.url.path
        return httpx.Response(200, json={"item": {"item_id": 5}})

    async with _client(handler) as client:
        assert await client.get_item(5) == {"item_id": 5}
    assert seen == {"auth": "Bearer token", "path": "/5"}


@pytest.mark.parametrize("status, words", [(401, "токен"), (404, "не найден"), (500, "500")])
async def test_get_item_errors(status, words):
    async with _client(lambda request: httpx.Response(status, json={"errors": ["x"]})) as client:
        with pytest.raises(LolzError, match=words):
            await client.get_item(5)


async def test_get_item_retries_once_on_429():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(429, headers={"Retry-After": "0"})
        return httpx.Response(200, json={"item": {"item_id": 5}})

    async with _client(handler) as client:
        assert await client.get_item(5) == {"item_id": 5}
    assert len(calls) == 2


def test_empty_token_is_refused():
    with pytest.raises(LolzError):
        LolzClient(" ", "https://api.test")
