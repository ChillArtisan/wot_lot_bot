"""Slides of a lot, styled as an army vehicle log book («формуляр»).

Sheet 1 is the form itself (account fields, tank tally, four photos), the
next sheets list the tier X–XI tanks, the premium tanks and the whole
hangar as printed tables. Every sheet carries the shop's rubber stamp.

Each slide is a self-contained HTML page (fonts and pictures inlined) sized
1280x720 for `render.render`. The Lolz item ID is never printed: the slides
go to another marketplace.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote

from jinja2 import Environment, FileSystemLoader

from wot_lot_bot.account import Tank, WotAccount
from wot_lot_bot.render import CSP

PACKAGE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = PACKAGE_DIR / "templates"
ASSETS_DIR = PACKAGE_DIR / "assets"

# (columns, rows) per sheet
BIG_GRID = (4, 3)
PREMIUM_GRID = (6, 5)
HANGAR_GRID = (7, 5)
HERO_TANKS = 4
# A shop name longer than this does not fit the stamp's rim, only its centre.
RING_NAME_LIMIT = 14
# Width budget of one of two fields sharing a form row, in px: labels are
# ~8 px a character, typed values exactly 15 (IBM Plex Mono at 25 px).
HALF_ROW = 330

# fontsource subsets → unicode-range
_UNICODE_RANGES = {
    "cyrillic": "U+0301,U+0400-045F,U+0490-0491,U+04B0-04B1,U+2116",
    "latin": ("U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+0304,"
              "U+0308,U+0329,U+2000-206F,U+20AC,U+2122,U+2191,U+2193,U+2212,U+2215,U+FEFF,U+FFFD"),
}
_FAMILIES = {"pt-sans-narrow": "PT Sans Narrow", "ibm-plex-mono": "IBM Plex Mono"}

_SILHOUETTE = (
    "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 160 100'>"
    "<g fill='#2E5D47' fill-opacity='.22'>"
    "<rect x='54' y='30' width='46' height='20' rx='6'/>"
    "<rect x='98' y='36' width='56' height='6' rx='3'/>"
    "<path d='M18 50h124l-8 18H26z'/>"
    "<rect x='16' y='68' width='128' height='16' rx='8'/></g></svg>"
)
PLACEHOLDER = "data:image/svg+xml;utf8," + quote(_SILHOUETTE)

MACHINES = ("машина", "машины", "машин")


@dataclass(frozen=True)
class Slide:
    name: str
    html: str


@lru_cache
def fonts_css() -> str:
    rules = []
    for path in sorted((ASSETS_DIR / "fonts").glob("*.woff2")):
        # pt-sans-narrow-cyrillic-700-normal
        *family, subset, weight, style = path.stem.split("-")
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        rules.append(
            f"@font-face{{font-family:'{_FAMILIES['-'.join(family)]}';font-style:{style};"
            f"font-weight:{weight};font-display:block;"
            f"src:url(data:font/woff2;base64,{encoded}) format('woff2');"
            f"unicode-range:{_UNICODE_RANGES[subset]}}}"
        )
    return "\n".join(rules)


@lru_cache
def _env() -> Environment:
    return Environment(loader=FileSystemLoader(TEMPLATES_DIR), autoescape=True,
                       trim_blocks=True, lstrip_blocks=True)


def fmt_int(value: int) -> str:
    # Narrow no-break space between thousands: "12 345".
    return f"{int(value):,}".replace(",", " ")


def plural(n: int, forms: tuple[str, str, str]) -> str:
    n = abs(n)
    if n % 10 == 1 and n % 100 != 11:
        return forms[0]
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return forms[1]
    return forms[2]


def _size(grid: tuple[int, int]) -> int:
    return grid[0] * grid[1]


def _chunks(items: tuple, size: int) -> list[tuple]:
    """Pages of at most `size`, evened out: 16 → 8 + 8, not 12 + 4."""
    if not items:
        return []
    pages = -(-len(items) // size)
    per_page = -(-len(items) // pages)
    return [items[i:i + per_page] for i in range(0, len(items), per_page)]


def _cells(tanks, images: dict[int, str]) -> list[dict]:
    return [
        {"name": t.name, "tier": t.tier_roman, "premium": t.is_premium, "nation": t.nation,
         "image": images.get(t.tank_id, PLACEHOLDER)}
        for t in tanks
    ]


def _tier_range(tanks: tuple[Tank, ...]) -> str:
    high, low = tanks[0].tier_roman, tanks[-1].tier_roman
    return f"уровень {high}" if high == low else f"уровни {high}–{low}"


def hero_tanks(account: WotAccount, count: int = HERO_TANKS) -> tuple[Tank, ...]:
    """Showcase: half tier X, half the highest premiums, the rest by tier."""
    picked: list[Tank] = []
    for pool in (account.tops[:count // 2],
                 [t for t in account.premiums if t.tier < 10][:count // 2],
                 account.tanks):
        for tank in pool:
            if len(picked) < count and tank not in picked:
                picked.append(tank)
    return tuple(sorted(picked, key=lambda t: t.sort_key))


def _stamp(watermark: str, now: datetime) -> dict:
    name = watermark.strip()
    centre = name or "К передаче"
    ring = "К ПЕРЕДАЧЕ НОВОМУ ВЛАДЕЛЬЦУ • "
    ring += f"МАГАЗИН {name.upper()} • " if name and len(name) <= RING_NAME_LIMIT else "К ПЕРЕДАЧЕ • "
    return {"ring": ring, "name": centre, "name_size": min(31, max(14, 270 // len(centre))),
            "date": f"{now.astimezone():%d.%m.%Y}"}


def _fits_half_row(label: str, value: str) -> bool:
    return len(label) * 8 + 14 + len(value) * 15 <= HALF_ROW


def _form_rows(pairs: list[list[tuple[str, str]]]) -> list[list[tuple[str, str]]]:
    """Drop empty fields; a pair that would not fit side by side takes two rows."""
    rows = []
    for pair in pairs:
        pair = [field for field in pair if field[1]]
        if len(pair) == 2 and not all(_fits_half_row(*field) for field in pair):
            rows += [[pair[0]], [pair[1]]]
        elif pair:
            rows.append(pair)
    return rows


def _cover_context(account: WotAccount, images: dict[int, str], now: datetime) -> dict:
    def date(value: datetime | None) -> str:
        return f"{value:%d.%m.%Y}" if value else ""

    win = "" if account.win_percent is None else f"{account.win_percent:.2f}".replace(".", ",") + " %"
    premium = f"до {account.premium_until:%d.%m.%Y}" if account.has_premium(now) else "нет"
    clan = f"[{account.clan_tag}]" if account.clan_tag else account.clan_name
    rows = _form_rows([
        [("Регион", account.region_phrase or account.region)],
        [("Зарегистрирована", date(account.registered)), ("Последний вход", date(account.last_activity))],
        [("Проведено боёв", fmt_int(account.battles)), ("Побед", win)],
        [("Личный рейтинг", fmt_int(account.rating) if account.rating else ""), ("Премиум-аккаунт", premium)],
        [("Золото", fmt_int(account.gold)), ("Кредиты", fmt_int(account.credits))],
        [("Игровой клиент", account.launcher), ("Клан", clan)],
    ])
    tiers = account.top_tiers
    return {
        "title": "Формуляр",
        "sub": "учётной записи World of Tanks",
        "rows": rows,
        "tally": [
            ("Машин в ангаре", account.tank_count),
            (f"из них {tiers} уровня", account.top_count),
            ("премиум", account.premium_count),
            (f"премиум {tiers} уровня", account.top_premium_count),
        ],
        "hero": _cells(hero_tanks(account), images),
    }


def build_slides(account: WotAccount, images: dict[int, str], *, watermark: str = "",
                 now: datetime | None = None) -> list[Slide]:
    now = now or datetime.now(timezone.utc)
    pages: list[tuple[str, str, dict]] = [("cover", "cover.html.j2", _cover_context(account, images, now))]
    # Big 4x3 cells while a section fits in two sheets, a dense table beyond.
    premium_grid = BIG_GRID if len(account.premiums) <= 2 * _size(BIG_GRID) else PREMIUM_GRID
    sections = (
        ("tops", f"Перечень машин {account.top_tiers} уровня", account.tops, BIG_GRID),
        ("premium", "Перечень премиум-машин", account.premiums, premium_grid),
        ("hangar", "Перечень всех машин", account.tanks, HANGAR_GRID),
    )
    for key, title, tanks, grid in sections:
        chunks = _chunks(tanks, _size(grid))
        dense = grid is not BIG_GRID
        for number, chunk in enumerate(chunks, 1):
            sub = f"{len(tanks)} {plural(len(tanks), MACHINES)}"
            if len(chunks) > 1:
                sub += f", часть {number} из {len(chunks)}"
            if dense:
                sub += f": {_tier_range(chunk)}"
            cols, rows = grid
            rows = -(-len(chunk) // cols) if dense else max(2, -(-len(chunk) // cols))
            pages.append((key if len(chunks) == 1 else f"{key}-{number}", "grid.html.j2", {
                "title": title, "sub": sub, "cells": _cells(chunk, images), "dense": dense,
                "cols": cols, "rows": rows,
                # On the premium sheets every tank is premium: no stamp on each.
                "mark_premium": key != "premium",
            }))

    base = {"csp": CSP, "fonts_css": fonts_css(),
            "css": (ASSETS_DIR / "slide.css").read_text(encoding="utf-8"),
            "stamp": _stamp(watermark, now), "sheet_total": len(pages)}
    slides = []
    for index, (name, template, context) in enumerate(pages, 1):
        html = _env().get_template(template).render(**base, **context, sheet=index)
        slides.append(Slide(name=f"{index:02d}-{name}.png", html=html))
    return slides
