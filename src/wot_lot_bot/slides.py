"""Slides of a lot: cover, tier X tanks, premium tanks, the whole hangar.

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

# (columns, rows) per slide
BIG_GRID = (4, 3)
PREMIUM_GRID = (6, 5)
HANGAR_GRID = (7, 5)
HERO_TANKS = 4

# fontsource subsets: file stem → unicode-range
_UNICODE_RANGES = {
    "cyrillic": "U+0301,U+0400-045F,U+0490-0491,U+04B0-04B1,U+2116",
    "latin": ("U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+0304,"
              "U+0308,U+0329,U+2000-206F,U+20AC,U+2122,U+2191,U+2193,U+2212,U+2215,U+FEFF,U+FFFD"),
}
_FONTS = {"oswald": "Oswald", "inter": "Inter"}

_SILHOUETTE = (
    "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 160 100'>"
    "<g fill='#ffffff' fill-opacity='.13'>"
    "<rect x='54' y='30' width='46' height='20' rx='6'/>"
    "<rect x='98' y='36' width='56' height='6' rx='3'/>"
    "<path d='M18 50h124l-8 18H26z'/>"
    "<rect x='16' y='68' width='128' height='16' rx='8'/></g></svg>"
)
PLACEHOLDER = "data:image/svg+xml;utf8," + quote(_SILHOUETTE)


@dataclass(frozen=True)
class Slide:
    name: str
    html: str


@lru_cache
def fonts_css() -> str:
    rules = []
    for path in sorted((ASSETS_DIR / "fonts").glob("*.woff2")):
        family, subset, weight = path.stem.split("-")
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        rules.append(
            f"@font-face{{font-family:'{_FONTS[family]}';font-style:normal;font-weight:{weight};"
            f"font-display:block;src:url(data:font/woff2;base64,{encoded}) format('woff2');"
            f"unicode-range:{_UNICODE_RANGES[subset]}}}"
        )
    return "\n".join(rules)


@lru_cache
def _env() -> Environment:
    env = Environment(loader=FileSystemLoader(TEMPLATES_DIR), autoescape=True,
                      trim_blocks=True, lstrip_blocks=True)
    env.filters["num"] = fmt_int
    return env


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


TANKS = ("танк", "танка", "танков")


def winrate_class(percent: float | None) -> str:
    """WoT community rating colours for the win rate."""
    if percent is None:
        return ""
    for limit, name in ((47, "wr-red"), (49, "wr-orange"), (52, "wr-yellow"),
                        (57, "wr-green"), (64, "wr-blue")):
        if percent < limit:
            return name
    return "wr-purple"


def _size(grid: tuple[int, int]) -> int:
    return grid[0] * grid[1]


def _chunks(items: tuple, size: int) -> list[tuple]:
    """Pages of at most `size`, evened out: 16 → 8 + 8, not 12 + 4."""
    if not items:
        return []
    pages = -(-len(items) // size)
    per_page = -(-len(items) // pages)
    return [items[i:i + per_page] for i in range(0, len(items), per_page)]


def _cards(tanks, images: dict[int, str]) -> list[dict]:
    return [
        {"name": t.name, "tier": t.tier_roman, "premium": t.is_premium,
         "image": images.get(t.tank_id, PLACEHOLDER), "has_image": t.tank_id in images}
        for t in tanks
    ]


def _tier_range(tanks: tuple[Tank, ...]) -> str:
    high, low = tanks[0].tier_roman, tanks[-1].tier_roman
    return f"Уровень {high}" if high == low else f"Уровни {high}–{low}"


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


def _cover_context(account: WotAccount, images: dict[int, str], now: datetime) -> dict:
    premium = None
    if account.has_premium(now):
        days = max(0, (account.premium_until - now).days)
        premium = {"until": f"{account.premium_until:%d.%m.%Y}",
                   "left": f"ещё {days} {plural(days, ('день', 'дня', 'дней'))}"}
    facts = []
    if account.rating:
        facts.append(("Личный рейтинг", fmt_int(account.rating)))
    if account.registered:
        facts.append(("Регистрация", f"{account.registered:%d.%m.%Y}"))
    if account.last_activity:
        facts.append(("Последний вход", f"{account.last_activity:%d.%m.%Y}"))
    if account.clan_tag or account.clan_name:
        facts.append(("Клан", f"[{account.clan_tag}]" if account.clan_tag else account.clan_name))
    if account.launcher:
        facts.append(("Клиент", account.launcher))
    win = account.win_percent
    return {
        "battles": account.battles,
        "win": None if win is None else f"{win:.2f}".rstrip("0").rstrip(".").replace(".", ",") + "%",
        "win_class": winrate_class(win),
        "gold": account.gold,
        "credits": account.credits,
        "premium": premium,
        "counters": [
            ("Танков", account.tank_count),
            (f"Топов {account.top_tiers}", account.top_count),
            ("Премов", account.premium_count),
            ("Топ-премов", account.top_premium_count),
        ],
        "hero": _cards(hero_tanks(account), images),
        "facts": facts,
    }


def build_slides(account: WotAccount, images: dict[int, str], *, watermark: str = "",
                 now: datetime | None = None) -> list[Slide]:
    now = now or datetime.now(timezone.utc)
    pages: list[tuple[str, str, dict]] = [
        ("cover", "cover.html.j2", {"heading": "Обзор аккаунта", **_cover_context(account, images, now)}),
    ]
    # Big 4x3 cards while a section fits in two slides, dense grid beyond.
    premium_grid = BIG_GRID if len(account.premiums) <= 2 * _size(BIG_GRID) else PREMIUM_GRID
    sections = (
        ("tops", f"Топы {account.top_tiers} уровня", account.tops, BIG_GRID),
        ("premium", "Премиум-техника", account.premiums, premium_grid),
        ("hangar", "Весь ангар", account.tanks, HANGAR_GRID),
    )
    for key, heading, tanks, grid in sections:
        chunks = _chunks(tanks, _size(grid))
        for number, chunk in enumerate(chunks, 1):
            note = f"{len(tanks)} {plural(len(tanks), TANKS)}"
            if grid is not BIG_GRID:
                note = f"{_tier_range(chunk)} · {note}"
            if len(chunks) > 1:
                note += f" · {number}/{len(chunks)}"
            name = key if len(chunks) == 1 else f"{key}-{number}"
            cols, rows = grid
            pages.append((name, "grid.html.j2", {
                "heading": heading, "note": note, "cards": _cards(chunk, images),
                "dense": grid is not BIG_GRID, "cols": cols,
                "rows": rows if grid is not BIG_GRID else min(rows, -(-len(chunk) // cols)),
            }))

    region = account.region_phrase or account.region
    base = {"csp": CSP, "fonts_css": fonts_css(),
            "css": (ASSETS_DIR / "slide.css").read_text(encoding="utf-8"),
            "region": region, "watermark": watermark.strip()}
    slides = []
    for index, (name, template, context) in enumerate(pages, 1):
        html = _env().get_template(template).render(
            **base, **context, pager=f"{index} / {len(pages)}")
        slides.append(Slide(name=f"{index:02d}-{name}.png", html=html))
    return slides
