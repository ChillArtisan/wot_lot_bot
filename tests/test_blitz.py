import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from wot_lot_bot.account import BLITZ, WOT, NotWotItem, from_item, games, scrub
from wot_lot_bot.slides import build_slides
from wot_lot_bot.summary import lot_text

FIXTURES = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 11, 3, tzinfo=timezone.utc)
SECRET = "hunter2-secret"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture
def raw() -> dict:
    """Blitz item as Lolz gave it before the October 2026 category merge."""
    item = _load("synthetic_blitz_item.json")
    item["loginData"] = {"login": "victim@mail.test", "password": SECRET}
    item["seller"] = {"username": "seller"}
    return item


@pytest.fixture
def merged() -> dict:
    """One item with both games: WoT under wot_*, Blitz under wot_blitz_* / blitz*."""
    item = {
        "item_id": 5, "category_id": 14, "wot_blitz": 1, "wot_region": "eu", "wotRegionPhrase": "EU",
        "wot_battle_count": 100, "wot_gold": 1, "wot_credits": 2, "wotLauncherTitle": "Wargaming.net Game Center",
        "wotTanks": {"7169": {"tank_id": 7169, "name": "IS-7", "tier": 10, "is_premium": 0,
                              "image_url": "//cdn.test/vehicle/ussr-R45_IS-7.png", "alt_image_url": ""}},
        "wot_blitz_battle_count": 200, "wot_blitz_gold": 3, "wot_blitz_credits": 4,
        "wot_blitz_premium_expires": int(datetime(2026, 12, 1, tzinfo=timezone.utc).timestamp()),
        "blitzTankCount": 2,
        "blitzTanks": {
            "385": {"tank_id": 385, "name": "Progetto M40 mod. 65", "tier": 10, "is_premium": 0,
                    "is_collectible": 0, "image_url": "", "secret": SECRET},
            "49": {"tank_id": 49, "name": "Type 59", "tier": 8, "is_premium": 1, "is_collectible": 0},
        },
        "blitzClan": {"name": "Blitz Clan", "tag": "BC", "emblem": SECRET},
        "loginData": {"password": SECRET},
    }
    return item


def test_old_blitz_item(raw):
    assert games(raw) == (BLITZ,)
    account = from_item(raw)
    assert account.game == BLITZ
    assert account.game_title == "Tanks Blitz"
    assert account.credits_name == "Серебро"
    assert account.battles == 9874
    assert account.win_percent == pytest.approx(54.79, abs=0.01)
    assert account.gold == 4250 and account.credits == 18_750_000
    assert account.has_premium(NOW)
    assert account.clan_tag == "BLTZ"
    assert len(account.tanks) == account.tank_count == 64
    assert len(account.tops) == account.top_count == 16
    assert len(account.premiums) == account.premium_count == 23
    assert account.top_premium_count == 3
    assert [t.name for t in account.collectibles] == ["VK 72.01 (K)", "Waffenträger auf Pz. IV",
                                                      "Spähpanzer Ru 251"]


def test_blitz_nation_comes_from_tank_id(raw):
    nations = {t.name: t.nation for t in from_item(raw).tanks}
    assert nations["Объект 140"] == "СССР"
    assert nations["Type 59"] == "Китай"
    assert nations["Chieftain Mk. 6"] == "Великобритания"
    assert nations["Kranvagn"] == "Европа"
    # Blitz's "other" nation (crossover vehicles) has no country to print.
    assert nations["Vindicator Ultramarines"] == ""


def test_blitz_tier_lists_premiums_then_collectibles(raw):
    tops = [t.name for t in from_item(raw).tops]
    assert tops[:4] == ["121B", "Chieftain Mk. 6", "Kampfpanzer 50 t", "VK 72.01 (K)"]


def test_blitz_ignores_wot_launcher(raw):
    raw["wotLauncherTitle"] = "Lesta Game Center"
    assert from_item(raw).launcher == ""


@pytest.mark.parametrize("changes", [
    # After the merge the old items sit in the WoT category, flag and tank records unchanged.
    {"category_id": 14},
    {"category_id": 14, "wot_blitz": 0},  # Blitz tank records alone tell
])
def test_old_shape_outside_blitz_category(raw, changes):
    raw.update(changes)
    assert games(raw) == (BLITZ,)


def test_blitz_flag_without_tank_lists():
    assert games({"category_id": 14, "wot_blitz": 1, "wot_battle_count": 5}) == (BLITZ,)
    assert games({"category_id": 14, "wot_blitz": 0, "wot_battle_count": 5}) == (WOT,)


def test_wot_item_stays_wot():
    item = _load("synthetic_item.json")
    item["wot_blitz"] = 0
    assert games(item) == (WOT,)
    account = from_item(item)
    assert account.game == WOT and account.game_title == "World of Tanks"
    assert account.credits_name == "Кредиты"
    with pytest.raises(NotWotItem):
        from_item(item, BLITZ)


def test_merged_item_has_both_games(merged):
    assert games(merged) == (WOT, BLITZ)
    wot, blitz = from_item(merged, WOT), from_item(merged, BLITZ)
    assert (wot.battles, wot.gold, wot.credits) == (100, 1, 2)
    assert (blitz.battles, blitz.gold, blitz.credits) == (200, 3, 4)
    assert [t.name for t in wot.tanks] == ["IS-7"] and wot.tanks[0].nation == "СССР"
    assert [t.name for t in blitz.tanks] == ["Progetto M40 mod. 65", "Type 59"]
    assert [t.nation for t in blitz.tanks] == ["Европа", "Китай"]
    assert blitz.has_premium(NOW) and not wot.has_premium(NOW)
    assert blitz.clan_tag == "BC"
    # Account-wide fields are shared; the WoT launcher is not Blitz's.
    assert blitz.region == wot.region == "EU"
    assert blitz.game_title == "World of Tanks Blitz"
    assert wot.launcher and not blitz.launcher


def test_two_games_give_two_sets_of_slides(merged):
    sets = [build_slides(from_item(merged, game), {}, now=NOW) for game in games(merged)]
    wot_names, blitz_names = ({s.name for s in slides} for slides in sets)
    assert "01-cover.png" in wot_names and "blitz-01-cover.png" in blitz_names
    assert not wot_names & blitz_names
    assert "World of Tanks Blitz" in sets[1][0].html and "World of Tanks Blitz" not in sets[0][0].html


def test_merged_item_without_wot_battles_is_blitz_only(merged):
    merged.update(wot_battle_count=0, wotTanks={})
    assert games(merged) == (BLITZ,)
    assert from_item(merged).game == BLITZ


def test_scrub_keeps_blitz_fields_only(merged):
    clean = scrub(merged)
    text = json.dumps(clean, ensure_ascii=False)
    assert SECRET not in text and "loginData" not in clean
    assert clean["wot_blitz_battle_count"] == 200
    assert clean["blitzClan"] == {"name": "Blitz Clan", "tag": "BC"}
    assert {"tank_id", "name", "tier", "is_premium", "is_collectible"} <= set(clean["blitzTanks"][0])


def test_blitz_slides(raw):
    slides = build_slides(from_item(raw), {}, watermark="SHOP", now=NOW)
    assert [s.name for s in slides] == [
        "blitz-01-cover.png", "blitz-02-tops-1.png", "blitz-03-tops-2.png",
        "blitz-04-premium-1.png", "blitz-05-premium-2.png", "blitz-06-hangar-1.png",
        "blitz-07-hangar-2.png"]
    cover = slides[0].html
    assert "учётной записи Tanks Blitz" in cover
    assert "Серебро" in cover and "Кредиты" not in cover
    assert "Игровой клиент" not in cover
    for slide in slides:
        assert SECRET not in slide.html
        assert "987654321" not in slide.html
        assert "SHOP" in slide.html
    hangar = "".join(s.html for s in slides if "hangar" in s.name)
    assert hangar.count('class="pstamp">колл<') == 3
    assert hangar.count('class="pstamp">прем<') == 23
    # A premium sheet stamps nothing: all of it is premium, and no collectible is.
    premium = "".join(s.html for s in slides if "premium" in s.name)
    assert 'class="pstamp"' not in premium


def test_blitz_lot_text(raw):
    text = lot_text(from_item(raw), NOW)
    assert text.startswith("Tanks Blitz · RU\n")
    assert "Серебро: 18 750 000" in text and "Кредиты" not in text
    assert "Коллекционных: 3" in text
    assert "Коллекционные (3): VK 72.01 (K), Waffenträger auf Pz. IV, Spähpanzer Ru 251" in text
    assert SECRET not in text


def test_wot_lot_text_unchanged():
    text = lot_text(from_item(_load("synthetic_item.json")), NOW)
    assert text.startswith("World of Tanks · RU\n")
    assert "Кредиты: 24 518 300" in text and "Коллекционн" not in text
