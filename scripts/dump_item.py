"""Save a Lolz listing as a scrubbed test fixture.

    python scripts/dump_item.py https://lzt.market/123456789/

Writes tests/fixtures/<id>.json with whitelisted WoT/Blitz fields only (no
login data, seller or buyer) and prints the names of all fields the API
returned, so new fields can be spotted and added to account.WOT_FIELDS.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from wot_lot_bot.account import WOT_FIELDS, from_item, games, scrub
from wot_lot_bot.config import get_settings
from wot_lot_bot.lolz import LolzClient, parse_item_id

FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures"


def _records(value) -> list[dict]:
    values = value.values() if isinstance(value, dict) else value if isinstance(value, list) else []
    return [record for record in values if isinstance(record, dict)]


async def main(link: str) -> None:
    item_id = parse_item_id(link)
    if not item_id:
        sys.exit(f"Not a Lolz link or ID: {link}")
    settings = get_settings()
    async with LolzClient(settings.lolz_api_token, settings.lolz_api_base) as client:
        item = await client.get_item(item_id)
    # Field names only: values may be secrets.
    print("All fields:", ", ".join(sorted(item)))
    for key in sorted(key for key in item if key.endswith("Tanks")):
        fields = sorted({name for record in _records(item[key]) for name in record})
        print(f"  {key} records:", ", ".join(fields) or "empty")
    # The Blitz names of merged items are a guess until a real item confirms them.
    unread = sorted(key for key in item if "blitz" in key.lower() and key not in WOT_FIELDS)
    if unread:
        print("Blitz fields the bot does not read:", ", ".join(unread))
    clean = scrub(item)
    FIXTURES.mkdir(parents=True, exist_ok=True)
    path = FIXTURES / f"{item_id}.json"
    path.write_text(json.dumps(clean, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Saved {path.name}")
    for game in games(clean):
        account = from_item(clean, game)
        print(f"{account.game_title}: {len(account.tanks)} tanks, {len(account.tops)} tops, "
              f"{len(account.premiums)} premiums, {len(account.collectibles)} collectibles, "
              f"{account.battles} battles")
        if account.tanks:
            print(f"  first tank: {account.tanks[0]}")
    for key in ("category_id", "wot_blitz", "wot_premium_expires", "wot_register_date", "wot_last_activity"):
        print(f"  {key} = {clean.get(key)!r}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    asyncio.run(main(sys.argv[1]))
