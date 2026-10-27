# wot_lot_bot

Telegram bot: a Lolz Market WoT listing link in → 1280x720 PNG slides (cover, tier X, premium, hangar) + lot text out. The owner uploads them to a PayGame lot.

## Layout
- `src/wot_lot_bot/lolz.py` — link parsing, `GET /{item_id}` (base `https://prod-api.lzt.market`, Bearer token).
- `account.py` — `scrub`/`from_item`: whitelist of WoT fields → `WotAccount`. The only way item data travels further.
- `slides.py` + `templates/*.j2` + `assets/slide.css` — HTML per slide; fonts (OFL, `assets/fonts`) and tank pictures inlined as data URIs.
- `render.py` — Chromium `--screenshot`, network cut off (ported from paygame_bot `paygame/screenshot.py`).
- `bot.py` — aiogram router, admins only; `summary.py` — lot text.

## Rules
- Bought listings carry login data. Never log, print, store or render anything outside `account.WOT_FIELDS`. Fixtures come only from `scripts/dump_item.py` (scrubbed). `raw/` is gitignored for a reason.
- Never print the Lolz item ID on slides: they go to another marketplace.
- Code, comments, commits in English; bot messages in Russian.
- Never touch `.env`.

## Commands
- Tests: `.venv/Scripts/python.exe -m pytest -q`
- Design loop: `.venv/Scripts/python.exe scripts/render_fixture.py tests/fixtures/<id>.json out` then look at `out/*.png`.
- Real listing → fixture: `.venv/Scripts/python.exe scripts/dump_item.py <link>`
- Run locally: `.venv/Scripts/python.exe -m wot_lot_bot` (Chrome is auto-detected on Windows).
- Server: `docker compose up -d --build` in `~/wot-lot-bot` on `ssh junction`; deploy only on explicit request.
