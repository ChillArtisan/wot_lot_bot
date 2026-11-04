# wot_lot_bot

Telegram bot: a Lolz Market World of Tanks or Tanks Blitz listing link in → 1280x720 PNG slides (cover, tier X, premium, hangar) + lot text out; for an item with both games the bot asks which one (or both) to make slides for (Blitz files are `blitz-*.png`). The owner uploads them to a PayGame lot.

## Layout
- `src/wot_lot_bot/lolz.py` — link parsing, `GET /{item_id}` (base `https://prod-api.lzt.market`, Bearer token).
- `account.py` — `scrub`/`games`/`from_item`: whitelist of WoT and Blitz fields → one `WotAccount` per game. The only way item data travels further.
- Blitz on Lolz: before the Oct 2026 merge, category 16 with the plain WoT field names and `wot_blitz` = 1 (confirmed by the API schema; Blitz tank records carry `is_collectible`). Merged items (category 14, Nov 2026 on live listings) put Blitz under `wot_blitz_*`/`wotBlitz*` (`account._blitz_name`); no Blitz launcher, rating or last activity. `dump_item.py` prints any Blitz field the bot does not read. Blitz nation comes from `(tank_id >> 4) & 15`.
- `slides.py` + `templates/*.j2` + `assets/slide.css` — HTML per slide in the «Формуляр» style (army vehicle log book: green print on grey-green form paper, typed values, violet rubber stamp with the shop name). Fonts PT Sans Narrow (print) and IBM Plex Mono (typewriter), OFL, in `assets/fonts`; fonts and tank pictures inlined as data URIs.
- `render.py` — Chromium `--screenshot`, network cut off (ported from paygame_bot `paygame/screenshot.py`).
- `bot.py` — aiogram router, admins only; `summary.py` — lot text.

## Rules
- Bought listings carry login data. Never log, print, store or render anything outside `account.WOT_FIELDS`. Fixtures come only from `scripts/dump_item.py` (scrubbed). `raw/` is gitignored for a reason.
- Never print the Lolz item ID on slides: they go to another marketplace.
- Code, comments, commits in English; bot messages in Russian.
- Never touch `.env`.

## Commands
- Tests: `.venv/Scripts/python.exe -m pytest -q`
- Design loop: `.venv/Scripts/python.exe scripts/render_fixture.py tests/fixtures/<id>.json out` then look at `out/*.png` (`synthetic_item.json` is WoT, `synthetic_blitz_item.json` is Blitz).
- Real listing → fixture: `.venv/Scripts/python.exe scripts/dump_item.py <link>`
- Run locally: `.venv/Scripts/python.exe -m wot_lot_bot` (Chrome is auto-detected on Windows).
- Server: `docker compose up -d --build` in `~/wot-lot-bot` on `ssh junction`; deploy only on explicit request.
