"""Render the slides of a fixture item to PNG files, without Telegram.

    python scripts/render_fixture.py tests/fixtures/synthetic_item.json [out_dir]

Tank pictures are downloaded (and cached in DATA_DIR) like the bot does.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from wot_lot_bot.account import from_item
from wot_lot_bot.config import get_settings
from wot_lot_bot.images import tank_images
from wot_lot_bot.render import find_browser, png_size, render
from wot_lot_bot.slides import build_slides


async def main(fixture: Path, out_dir: Path) -> None:
    settings = get_settings()
    browser = find_browser(settings.chromium_path)
    if not browser:
        sys.exit("Chromium not found: set CHROMIUM_PATH")
    account = from_item(json.loads(fixture.read_text(encoding="utf-8")))
    images = await tank_images(account.tanks, settings.tank_cache_dir)
    print(f"{len(account.tanks)} tanks, {len(images)} pictures")
    out_dir.mkdir(parents=True, exist_ok=True)
    for slide in build_slides(account, images, watermark=settings.watermark or "SHOP NAME"):
        data = await render(slide.html, browser=browser)
        (out_dir / slide.name).write_bytes(data)
        (out_dir / slide.name).with_suffix(".html").write_text(slide.html, encoding="utf-8")
        print(slide.name, "x".join(map(str, png_size(data))))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    asyncio.run(main(Path(sys.argv[1]), Path(sys.argv[2] if len(sys.argv) > 2 else "out")))
