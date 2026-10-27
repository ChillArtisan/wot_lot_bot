"""Lolz Market API: one call, GET /{item_id}.

The response for an item the token owner bought carries login data. Nothing
here logs or returns the raw payload beyond `get_item`; callers normalize it
through `account.from_item`, which keeps only whitelisted WoT fields.
"""
from __future__ import annotations

import asyncio
import logging
import re
from urllib.parse import urlsplit

import httpx

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 30
MAX_RETRY_WAIT_SECONDS = 30
# Market item IDs are 6+ digits today; 4 keeps old listings and rules out
# tier numbers and years that might sit in a pasted title.
_ID = re.compile(r"^\d{4,12}$")
_MARKET_HOSTS = ("lzt.market", "lolz.market", "lolz.live", "lolz.guru", "zelenka.guru")


class LolzError(RuntimeError):
    """Request failed. The text is shown to the owner as is."""


def parse_item_id(text: str) -> int | None:
    """Item ID from a market link (`https://lzt.market/123456/`) or a bare number."""
    text = (text or "").strip()
    if _ID.match(text):
        return int(text)
    for token in text.split():
        candidate = token if "://" in token else f"https://{token}"
        parts = urlsplit(candidate)
        host = (parts.hostname or "").lower()
        if not any(host == known or host.endswith("." + known) for known in _MARKET_HOSTS):
            continue
        for segment in parts.path.split("/"):
            if _ID.match(segment):
                return int(segment)
    return None


def _retry_after(response: httpx.Response) -> float:
    raw = response.headers.get("Retry-After", "")
    try:
        wait = float(raw)
    except ValueError:
        wait = 5.0
    return max(1.0, min(wait, MAX_RETRY_WAIT_SECONDS))


class LolzClient:
    def __init__(self, token: str, base_url: str, *, transport: httpx.AsyncBaseTransport | None = None):
        if not token.strip():
            raise LolzError("Не задан LOLZ_API_TOKEN в .env.")
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {token.strip()}", "Accept": "application/json"},
            timeout=TIMEOUT_SECONDS,
            transport=transport,
        )

    async def __aenter__(self) -> LolzClient:
        return self

    async def __aexit__(self, *exc) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def get_item(self, item_id: int) -> dict:
        """Raw `item` object of a listing."""
        for attempt in range(2):
            try:
                response = await self._client.get(f"/{item_id}")
            except httpx.HTTPError as exc:
                logger.warning("Lolz request failed: %s", type(exc).__name__)
                raise LolzError("Lolz не отвечает, попробуй ещё раз через минуту.") from None
            if response.status_code == 429 and attempt == 0:
                await asyncio.sleep(_retry_after(response))
                continue
            break
        status = response.status_code
        if status == 401:
            raise LolzError("Lolz не принял токен: проверь LOLZ_API_TOKEN.")
        if status == 403:
            raise LolzError("Lolz не даёт доступ к этому лоту.")
        if status == 404:
            raise LolzError(f"Лот {item_id} не найден на Lolz.")
        if status == 429:
            raise LolzError("Lolz ограничил частоту запросов, попробуй через минуту.")
        if status >= 400:
            raise LolzError(f"Lolz ответил ошибкой {status}.")
        try:
            item = response.json().get("item")
        except ValueError:
            item = None
        if not isinstance(item, dict):
            raise LolzError("Lolz вернул ответ без данных лота.")
        return item
