"""Save a Lolz listing as a scrubbed test fixture.

    python scripts/dump_item.py https://lzt.market/123456789/

Writes tests/fixtures/<id>.json with whitelisted WoT fields only (no login
data, seller or buyer) and prints the names of all fields the API returned,
so new WoT fields can be spotted and added to account.WOT_FIELDS.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from wot_lot_bot.account import from_item, scrub
from wot_lot_bot.config import get_settings
from wot_lot_bot.lolz import LolzClient, parse_item_id

FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures"


async def main(link: str) -> None:
    item_id = parse_item_id(link)
    if not item_id:
        sys.exit(f"Not a Lolz link or ID: {link}")
    settings = get_settings()
    async with LolzClient(settings.lolz_api_token, settings.lolz_api_base) as client:
        item = await client.get_item(item_id)
    # Field names only: values may be secrets.
    print("All fields:", ", ".join(sorted(item)))
    clean = scrub(item)
    FIXTURES.mkdir(parents=True, exist_ok=True)
    path = FIXTURES / f"{item_id}.json"
    path.write_text(json.dumps(clean, ensure_ascii=False, indent=1), encoding="utf-8")
    account = from_item(clean)
    print(f"Saved {path.name}: {len(account.tanks)} tanks, {len(account.tops)} tops, "
          f"{len(account.premiums)} premiums")
    for key in ("wot_premium_expires", "wot_register_date", "wot_last_activity"):
        print(f"  {key} = {clean.get(key)!r}")
    if account.tanks:
        tank = account.tanks[0]
        print(f"  first tank: {tank}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    asyncio.run(main(sys.argv[1]))
