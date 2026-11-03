"""WoT or Tanks Blitz account as the slides need it, built from a Lolz `item`.

Only the fields listed in `WOT_FIELDS` are read. Everything else in the item
(login data, seller, buyer, links) never leaves `from_item`, so it cannot end
up on a slide, in a log line or in a test fixture.

Both games live in the Lolz World of Tanks category. Until October 2026 Blitz
had a category of its own (16) whose items carried exactly the WoT fields
(`wot_battle_count`, `wotTanks`, ...) plus `wot_blitz` = 1; such an item is
read through the WoT names. Since the merge one item may hold both games. The
Blitz half is expected under the names Lolz gives a game in its other merged
categories (`riot_valorant_level`, `mihoyo_genshin_level`, `valorantInventory`),
that is `wot_blitz_gold`, `blitzTanks`: see `_blitz_name`. Those names are not
in the API docs yet; `scripts/dump_item.py` lists what a real item holds.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

WOT = "wot"
BLITZ = "blitz"
GAMES = (WOT, BLITZ)
BLITZ_CATEGORY = 16

# Fields of the account as a whole.
_COMMON = ("item_id", "category_id", "title", "wot_blitz",
           "wot_region", "wotRegionPhrase", "wot_register_date")
# Fields of one game, under their WoT names.
_GAME = (
    "wotLauncherTitle", "wot_mobile",
    "wot_battle_count", "wot_win_count", "wot_loss_count", "wot_win_count_percents",
    "wot_global_rating",
    "wot_gold", "wot_credits",
    "wot_premium", "wot_premium_expires", "wot_last_activity",
    "wotTankCount", "wotPremiumTankCount",
    "wot_top_tanks", "wot_premium_tanks", "wot_top_premium_tanks",
    "wotTanks", "wotTopTanks", "wotPremiumTanks", "wotTopPremiumTanks",
    "wot_clan", "wot_has_clan", "wotClan",
)
_TANK_LISTS = ("wotTanks", "wotTopTanks", "wotPremiumTanks", "wotTopPremiumTanks")


def _blitz_name(key: str) -> str:
    """Blitz twin of a WoT field in a merged item: wot_gold → wot_blitz_gold, wotTanks → blitzTanks."""
    return "wot_blitz_" + key.removeprefix("wot_") if key.startswith("wot_") else "blitz" + key.removeprefix("wot")


WOT_FIELDS = _COMMON + _GAME + tuple(_blitz_name(key) for key in _GAME)
TANK_FIELDS = ("tank_id", "name", "short_name", "tier", "is_premium", "is_collectible",
               "image_url", "alt_image_url")
CLAN_FIELDS = ("name", "tag", "members_count")
TOP_TIER = 10

ROMAN = {1: "I", 2: "II", 3: "III", 4: "IV", 5: "V", 6: "VI", 7: "VII", 8: "VIII", 9: "IX", 10: "X", 11: "XI"}
# Nation code that starts a WoT vehicle picture name: .../vehicle/usa-A195_Gorilla.png
NATIONS = {"usa": "США", "ussr": "СССР", "germany": "Германия", "uk": "Великобритания",
           "france": "Франция", "china": "Китай", "japan": "Япония", "czech": "Чехословакия",
           "sweden": "Швеция", "poland": "Польша", "italy": "Италия", "intunion": "Сборная"}
# Blitz pictures have no such prefix, but a tank_id keeps the nation in bits
# 4-7. 7 is Blitz's "other" (crossover vehicles): no country to print.
BLITZ_NATIONS = ("СССР", "Германия", "США", "Китай", "Франция", "Великобритания", "Япония", "", "Европа")


class NotWotItem(ValueError):
    """The listing has no World of Tanks or Tanks Blitz data."""


def scrub(item: dict) -> dict:
    """Copy of `item` with only whitelisted fields: safe to store as a fixture."""
    clean = {key: item[key] for key in WOT_FIELDS if key in item}
    for key in (*_TANK_LISTS, *map(_blitz_name, _TANK_LISTS)):
        if key in clean:
            clean[key] = [
                {k: tank[k] for k in TANK_FIELDS if k in tank}
                for tank in _tank_list(clean[key])
            ]
    for key in ("wotClan", _blitz_name("wotClan")):
        if isinstance(clean.get(key), dict):
            clean[key] = {k: clean[key][k] for k in CLAN_FIELDS if k in clean[key]}
    return clean


@dataclass(frozen=True)
class Tank:
    tank_id: int
    name: str
    tier: int
    is_premium: bool
    image_url: str = ""
    alt_image_url: str = ""
    is_collectible: bool = False
    nation: str = ""  # in Russian, "" when unknown

    @property
    def tier_roman(self) -> str:
        return ROMAN.get(self.tier, str(self.tier))

    @property
    def sort_key(self) -> tuple:
        return (-self.tier, not self.is_premium, not self.is_collectible, self.name.casefold())


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
    game: str = WOT

    @property
    def game_title(self) -> str:
        if self.game != BLITZ:
            return "World of Tanks"
        # Lesta runs the Russian server under its own name since 2023.
        return "Tanks Blitz" if self.region == "RU" else "World of Tanks Blitz"

    @property
    def credits_name(self) -> str:
        """The second currency as the game's Russian client calls it."""
        return "Серебро" if self.game == BLITZ else "Кредиты"

    @property
    def tops(self) -> tuple[Tank, ...]:
        return tuple(t for t in self.tanks if t.tier >= TOP_TIER)

    @property
    def premiums(self) -> tuple[Tank, ...]:
        return tuple(t for t in self.tanks if t.is_premium)

    @property
    def collectibles(self) -> tuple[Tank, ...]:
        return tuple(t for t in self.tanks if t.is_collectible)

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


def _wot_nation(*urls: str) -> str:
    for url in urls:
        stem = url.rsplit("/", 1)[-1]
        if "-" in stem and stem.split("-", 1)[0] in NATIONS:
            return NATIONS[stem.split("-", 1)[0]]
    return ""


def _blitz_nation(tank_id: int) -> str:
    code = (tank_id >> 4) & 0xF
    return BLITZ_NATIONS[code] if code < len(BLITZ_NATIONS) else ""


def _tank(raw: dict, game: str) -> Tank | None:
    tank_id = _int(raw.get("tank_id"))
    name = _str(raw.get("name") or raw.get("short_name"))
    tier = _int(raw.get("tier"))
    if not tank_id or not name or tier <= 0:
        return None
    image_url, alt_image_url = _url(raw.get("image_url")), _url(raw.get("alt_image_url"))
    return Tank(
        tank_id=tank_id,
        name=name,
        tier=tier,
        is_premium=bool(_int(raw.get("is_premium"))),
        image_url=image_url,
        alt_image_url=alt_image_url,
        is_collectible=bool(_int(raw.get("is_collectible"))),
        nation=_blitz_nation(tank_id) if game == BLITZ else _wot_nation(image_url, alt_image_url),
    )


def _plain_game(item: dict) -> str:
    """The game the wot_* fields describe in an item without a Blitz half."""
    if _int(item.get("category_id")) == BLITZ_CATEGORY:
        return BLITZ
    tanks = [tank for key in _TANK_LISTS for tank in _tank_list(item.get(key))]
    if tanks:
        # Blitz tank records carry is_collectible, WoT ones do not.
        return BLITZ if any("is_collectible" in tank for tank in tanks) else WOT
    return BLITZ if _int(item.get("wot_blitz")) else WOT


def _views(item: dict) -> dict[str, dict]:
    """Fields of every game in a scrubbed item, under the WoT names."""
    common = {key: item[key] for key in _COMMON if key in item}
    plain = {key: item[key] for key in _GAME if key in item}
    blitz = {key: item[_blitz_name(key)] for key in _GAME if _blitz_name(key) in item}
    if blitz:
        return {WOT: common | plain, BLITZ: common | blitz}
    return {_plain_game(item): common | plain}


def _has_data(view: dict) -> bool:
    return (_int(view.get("wot_battle_count")) > 0 or _int(view.get("wotTankCount")) > 0
            or any(_tank_list(view.get(key)) for key in _TANK_LISTS))


def _is_tank_account(view: dict) -> bool:
    return any(key in view for key in ("wot_battle_count", "wot_region", "wotTankCount", *_TANK_LISTS))


def games(item: dict) -> tuple[str, ...]:
    """Games the item holds an account of, WoT first.

    An account with no battles and no tanks counts only when there is nothing else.
    """
    views = _views(scrub(item))
    found = tuple(game for game in GAMES if game in views and _has_data(views[game]))
    if found:
        return found
    found = tuple(game for game in GAMES if game in views and _is_tank_account(views[game]))
    if found:
        return found[:1]
    raise NotWotItem("Это не лот World of Tanks или Tanks Blitz: у него нет данных по танкам.")


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


def from_item(item: dict, game: str | None = None) -> WotAccount:
    """Account of `game` in the item; by default of its first game (see `games`)."""
    game = game or games(item)[0]
    item = _views(scrub(item)).get(game)
    if item is None:
        raise NotWotItem("В этом лоте нет аккаунта Tanks Blitz." if game == BLITZ
                         else "В этом лоте нет аккаунта World of Tanks.")
    tanks: dict[int, Tank] = {}
    for key in _TANK_LISTS:
        for raw in _tank_list(item.get(key)):
            tank = _tank(raw, game)
            if tank and tank.tank_id not in tanks:
                tanks[tank.tank_id] = tank
    if not tanks and not _is_tank_account(item):
        raise NotWotItem("Это не лот World of Tanks или Tanks Blitz: у него нет данных по танкам.")
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
        # Blitz is played from a phone or Steam: the WoT launcher means nothing there.
        launcher="" if game == BLITZ else _str(item.get("wotLauncherTitle")),
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
        game=game,
    )
