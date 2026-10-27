"""Tank pictures as `data:` URIs, cached on disk.

Chromium renders offline, so every picture is fetched here and inlined. The
URLs come from the Lolz response: only http(s), only real image bytes, capped
in size. A tank whose picture fails gets a silhouette in the template.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
from collections.abc import Iterable
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from wot_lot_bot.account import Tank

logger = logging.getLogger(__name__)

MAX_IMAGE_BYTES = 2_000_000
PARALLEL = 8
TIMEOUT_SECONDS = 20

_SIGNATURES = (
    (b"\x89PNG", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF8", "image/gif"),
    (b"RIFF", "image/webp"),
)


def _mime(data: bytes) -> str | None:
    for magic, mime in _SIGNATURES:
        if data.startswith(magic):
            if mime == "image/webp" and data[8:12] != b"WEBP":
                return None
            return mime
    head = data[:512].lstrip().lower()
    if head.startswith(b"<svg") or (head.startswith(b"<?xml") and b"<svg" in head):
        return "image/svg+xml"
    return None


def data_uri(data: bytes) -> str | None:
    mime = _mime(data)
    if not mime:
        return None
    return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"


def _cache_path(cache_dir: Path, url: str) -> Path:
    return cache_dir / (hashlib.sha256(url.encode("utf-8")).hexdigest()[:32] + ".img")


async def _fetch(client: httpx.AsyncClient, url: str, cache_dir: Path) -> bytes | None:
    if urlsplit(url).scheme not in ("http", "https"):
        return None
    cached = _cache_path(cache_dir, url)
    if cached.is_file():
        return cached.read_bytes()
    try:
        async with client.stream("GET", url) as response:
            if response.status_code != 200:
                return None
            chunks, size = [], 0
            async for chunk in response.aiter_bytes():
                size += len(chunk)
                if size > MAX_IMAGE_BYTES:
                    return None
                chunks.append(chunk)
    except httpx.HTTPError as exc:
        logger.info("Tank image failed (%s): %s", type(exc).__name__, url)
        return None
    data = b"".join(chunks)
    if not _mime(data):
        return None
    cache_dir.mkdir(parents=True, exist_ok=True)
    tmp = cached.with_suffix(".part")
    tmp.write_bytes(data)
    tmp.replace(cached)
    return data


async def tank_images(tanks: Iterable[Tank], cache_dir: Path) -> dict[int, str]:
    """tank_id → data URI for every tank whose picture could be loaded."""
    tanks = list(tanks)
    semaphore = asyncio.Semaphore(PARALLEL)
    result: dict[int, str] = {}
    async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS, follow_redirects=True,
                                 headers={"User-Agent": "Mozilla/5.0"}) as client:
        async def one(tank: Tank) -> None:
            async with semaphore:
                for url in (tank.image_url, tank.alt_image_url):
                    if not url:
                        continue
                    data = await _fetch(client, url, cache_dir)
                    uri = data_uri(data) if data else None
                    if uri:
                        result[tank.tank_id] = uri
                        return

        await asyncio.gather(*(one(tank) for tank in tanks))
    return result
