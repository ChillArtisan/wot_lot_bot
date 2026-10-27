"""WoT account as the slides need it, built from a Lolz `item`.

Only the fields listed in `WOT_FIELDS` are read. Everything else in the item
(login data, seller, buyer, links) never leaves `from_item`, so it cannot end
up on a slide, in a log line or in a test fixture.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

WOT_FIELDS = (
    "item_id", "category_id", "title",
    "wot_region", "wotRegionPhrase", "wotLauncherTitle", "wot_mobile",
    "wot_battle_count", "wot_win_count", "wot_loss_count", "wot_win_count_percents",
    "wot_global_rating",
    "wot_gold", "wot_credits",
    "wot_premium", "wot_premium_expires",
    "wot_register_date", "wot_last_activity",
    "wotTankCount", "wotPremiumTankCount",
    "wot_top_tanks", "wot_premium_tanks", "wot_top_premium_tanks",
    "wotTanks", "wotTopTanks", "wotPremiumTanks", "wotTopPremiumTanks",
    "wot_clan", "wot_has_clan", "wotClan",
)
TANK_FIELDS = ("tank_id", "name", "short_name", "tier", "is_premium", "image_url", "alt_image_url")
CLAN_FIELDS = ("name", "tag", "members_count")
TOP_TIER = 10

ROMAN = {1: "I", 2: "II", 3: "III", 4: "IV", 5: "V", 6: "VI", 7: "VII", 8: "VIII", 9: "IX", 10: "X", 11: "XI"}


class NotWotItem(ValueError):
    """The listing has no World of Tanks data."""


def scrub(item: dict) -> dict:
    """Copy of `item` with only whitelisted fields: safe to store as a fixture."""
    clean = {key: item[key] for key in WOT_FIELDS if key in item}
    for key in ("wotTanks", "wotTopTanks", "wotPremiumTanks", "wotTopPremiumTanks"):
        if key in clean:
            clean[key] = [
                {k: tank[k] for k in TANK_FIELDS if k in tank}
                for tank in _tank_list(clean[key])
            ]
    if isinstance(clean.get("wotClan"), dict):
        clean["wotClan"] = {k: clean["wotClan"][k] for k in CLAN_FIELDS if k in clean["wotClan"]}
    return clean


@dataclass(frozen=True)
class Tank:
    tank_id: int
    name: str
    tier: int
    is_premium: bool
    image_url: str = ""
    alt_image_url: str = ""

    @property
    def tier_roman(self) -> str:
        return ROMAN.get(self.tier, str(self.tier))

    @property
    def sort_key(self) -> tuple:
        return (-self.tier, not self.is_premium, self.name.casefold())


@dataclass(frozen=True)
class WotAccount:
    item_id: int
    region: str
    region_phrase: str
    launcher: str
    battles: int
    win_percent: float | None
    rating: int
    gold: int
    credits: int
    premium_until: datetime | None
    registered: datetime | None
    last_activity: datetime | None
    clan_name: str
    clan_tag: str
    tanks: tuple[Tank, ...] = field(default=())
    tank_count: int = 0
    premium_count: int = 0
    top_count: int = 0
    top_premium_count: int = 0

    @property
    def tops(self) -> tuple[Tank, ...]:
        return tuple(t for t in self.tanks if t.tier >= TOP_TIER)

    @property
    def premiums(self) -> tuple[Tank, ...]:
        return tuple(t for t in self.tanks if t.is_premium)

    @property
    def top_tiers(self) -> str:
        """"X", or "X–XI" once the account has tier XI."""
        high = max((t.tier for t in self.tanks), default=TOP_TIER)
        return ROMAN[TOP_TIER] if high <= TOP_TIER else f"{ROMAN[TOP_TIER]}–{ROMAN.get(high, high)}"

    def has_premium(self, now: datetime | None = None) -> bool:
        now = now or datetime.now(timezone.utc)
        return self.premium_until is not None and self.premium_until > now


def _int(value, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _str(value) -> str:
    return " ".join(str(value).split()) if value not in (None, False) else ""


def _time(value) -> datetime | None:
    stamp = _int(value)
    if stamp <= 0:
        return None
    if stamp > 10**11:  # milliseconds
        stamp //= 1000
    try:
        return datetime.fromtimestamp(stamp, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


def _url(value) -> str:
    # The API gives protocol-relative links: //api.worldoftanks.com/static/...
    url = _str(value)
    return "https:" + url if url.startswith("//") else url


def _tank_list(raw) -> list[dict]:
    if isinstance(raw, dict):
        raw = list(raw.values())
    if not isinstance(raw, list):
        return []
    return [tank for tank in raw if isinstance(tank, dict)]


def _tank(raw: dict) -> Tank | None:
    tank_id = _int(raw.get("tank_id"))
    name = _str(raw.get("name") or raw.get("short_name"))
    tier = _int(raw.get("tier"))
    if not tank_id or not name or tier <= 0:
        return None
    return Tank(
        tank_id=tank_id,
        name=name,
        tier=tier,
        is_premium=bool(_int(raw.get("is_premium"))),
        image_url=_url(raw.get("image_url")),
        alt_image_url=_url(raw.get("alt_image_url")),
    )


def _win_percent(item: dict) -> float | None:
    battles = _int(item.get("wot_battle_count"))
    wins = _int(item.get("wot_win_count"), -1)
    if battles > 0 and wins >= 0:
        return round(wins * 100 / battles, 2)
    raw = item.get("wot_win_count_percents")
    try:
        return float(raw) if raw is not None and battles > 0 else None
    except (TypeError, ValueError):
        return None


def from_item(item: dict) -> WotAccount:
    item = scrub(item)
    tanks: dict[int, Tank] = {}
    for key in ("wotTanks", "wotTopTanks", "wotPremiumTanks", "wotTopPremiumTanks"):
        for raw in _tank_list(item.get(key)):
            tank = _tank(raw)
            if tank and tank.tank_id not in tanks:
                tanks[tank.tank_id] = tank
    has_stats = any(key in item for key in ("wot_battle_count", "wot_region", "wotTankCount"))
    if not tanks and not has_stats:
        raise NotWotItem("Это не лот World of Tanks: у него нет данных по танкам.")
    ordered = tuple(sorted(tanks.values(), key=lambda t: t.sort_key))

    clan = item.get("wotClan") if isinstance(item.get("wotClan"), dict) else {}
    premium_until = _time(item.get("wot_premium_expires"))
    if premium_until is None and _int(item.get("wot_premium")) > 10**9:
        premium_until = _time(item.get("wot_premium"))

    tops = sum(1 for t in ordered if t.tier >= TOP_TIER)
    premiums = sum(1 for t in ordered if t.is_premium)
    top_premiums = sum(1 for t in ordered if t.tier >= TOP_TIER and t.is_premium)
    return WotAccount(
        item_id=_int(item.get("item_id")),
        region=_str(item.get("wot_region")).upper(),
        region_phrase=_str(item.get("wotRegionPhrase")),
        launcher=_str(item.get("wotLauncherTitle")),
        battles=_int(item.get("wot_battle_count")),
        win_percent=_win_percent(item),
        rating=_int(item.get("wot_global_rating")),
        gold=_int(item.get("wot_gold")),
        credits=_int(item.get("wot_credits")),
        premium_until=premium_until,
        registered=_time(item.get("wot_register_date")),
        last_activity=_time(item.get("wot_last_activity")),
        clan_name=_str(clan.get("name")),
        clan_tag=_str(clan.get("tag")),
        tanks=ordered,
        # The API counters are the source of truth when the tank lists are
        # trimmed; the lists win when they hold more than the counter says.
        tank_count=max(_int(item.get("wotTankCount")), len(ordered)),
        premium_count=max(_int(item.get("wotPremiumTankCount") or item.get("wot_premium_tanks")), premiums),
        top_count=max(_int(item.get("wot_top_tanks")), tops),
        top_premium_count=max(_int(item.get("wot_top_premium_tanks")), top_premiums),
    )
