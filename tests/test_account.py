import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from wot_lot_bot.account import WOT_FIELDS, NotWotItem, from_item, scrub
from wot_lot_bot.slides import build_slides, hero_tanks
from wot_lot_bot.summary import lot_text

FIXTURE = Path(__file__).parent / "fixtures" / "synthetic_item.json"
NOW = datetime(2026, 10, 27, tzinfo=timezone.utc)
SECRET = "hunter2-secret"


@pytest.fixture
def raw() -> dict:
    item = json.loads(FIXTURE.read_text(encoding="utf-8"))
    # What a bought listing carries on top of the WoT data.
    item["loginData"] = {"login": "victim@mail.test", "password": SECRET, "raw": f"x:{SECRET}"}
    item["emailLoginData"] = {"password": SECRET}
    item["seller"] = {"username": "seller"}
    return item


def test_scrub_drops_everything_but_wot_fields(raw):
    clean = scrub(raw)
    assert "loginData" not in clean and "emailLoginData" not in clean and "seller" not in clean
    assert SECRET not in json.dumps(clean, ensure_ascii=False)


def test_fixtures_on_disk_hold_no_login_data():
    for path in FIXTURE.parent.glob("*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        assert set(data) <= set(WOT_FIELDS), path.name


def test_from_item(raw):
    account = from_item(raw)
    assert account.battles == 18452
    assert account.win_percent == pytest.approx(53.33, abs=0.01)
    assert account.gold == 12840
    assert account.has_premium(NOW)
    assert account.registered.year == 2013
    assert account.clan_tag == "SYNTH"
    assert len(account.tanks) == account.tank_count == 46
    assert len(account.tops) == 14
    assert len(account.premiums) == 16
    tiers = [t.tier for t in account.tanks]
    assert tiers == sorted(tiers, reverse=True)
    tier8 = [t for t in account.tanks if t.tier == 8]
    assert tier8[0].is_premium and not tier8[-1].is_premium


def test_tank_lists_as_list_and_merged_without_duplicates():
    tank = {"tank_id": 1, "name": "ИС-7", "tier": 10, "is_premium": 0}
    account = from_item({"wot_battle_count": 1, "wotTanks": [tank], "wotTopTanks": {"1": tank}})
    assert len(account.tanks) == 1


def test_not_wot_item():
    with pytest.raises(NotWotItem):
        from_item({"item_id": 1, "title": "Steam account"})


def test_millisecond_timestamps():
    account = from_item({"wot_battle_count": 1, "wot_register_date": 1361145600000})
    assert account.registered.year == 2013


def test_slides_never_show_login_data_or_lolz_id(raw):
    account = from_item(raw)
    slides = build_slides(account, {}, watermark="SHOP", now=NOW)
    names = [s.name for s in slides]
    assert names == ["01-cover.png", "02-tops-1.png", "03-tops-2.png", "04-premium-1.png",
                     "05-premium-2.png", "06-hangar-1.png", "07-hangar-2.png"]
    for slide in slides:
        assert SECRET not in slide.html
        assert "123456789" not in slide.html
        assert "SHOP" in slide.html
    assert SECRET not in lot_text(account, NOW)


def test_pages_are_evened_out(raw):
    account = from_item(raw)
    slides = build_slides(account, {}, now=NOW)
    # 14 tops → 7 + 7, 16 premiums → 8 + 8
    assert slides[1].html.count('class="card') == 7
    assert slides[3].html.count('class="card') == 8


def test_no_tops_no_premium_slides():
    tank = {"tank_id": 1, "name": "Т-34", "tier": 5, "is_premium": 0}
    slides = build_slides(from_item({"wot_battle_count": 1, "wotTanks": [tank]}), {}, now=NOW)
    assert [s.name for s in slides] == ["01-cover.png", "02-hangar.png"]


def test_hero_mixes_tops_and_premiums(raw):
    hero = hero_tanks(from_item(raw))
    assert len(hero) == 4
    assert sum(t.tier == 10 for t in hero) == 2
    assert sum(t.is_premium for t in hero) == 2


def test_tank_names_are_escaped():
    tank = {"tank_id": 1, "name": "<script>x</script>", "tier": 5, "is_premium": 0}
    slides = build_slides(from_item({"wot_battle_count": 1, "wotTanks": [tank]}), {}, now=NOW)
    assert "<script>x" not in slides[-1].html


def test_protocol_relative_image_urls():
    tank = {"tank_id": 1, "name": "Gorilla", "tier": 11, "is_premium": 0,
            "image_url": "//api.worldoftanks.com/static/x.png", "alt_image_url": ""}
    account = from_item({"wot_battle_count": 1, "wotTanks": [tank]})
    assert account.tanks[0].image_url == "https://api.worldoftanks.com/static/x.png"
    assert account.top_tiers == "X–XI"
    assert len(account.tops) == 1


def test_many_premiums_switch_to_dense_grid():
    tanks = [{"tank_id": i, "name": f"P{i}", "tier": 8, "is_premium": 1} for i in range(1, 31)]
    slides = build_slides(from_item({"wot_battle_count": 1, "wotTanks": tanks}), {}, now=NOW)
    premium = [s for s in slides if "premium" in s.name]
    assert len(premium) == 1 and 'class="tanks dense"' in premium[0].html
