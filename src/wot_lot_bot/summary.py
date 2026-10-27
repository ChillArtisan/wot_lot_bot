"""Plain-text summary sent after the slides, ready to paste into the lot."""
from __future__ import annotations

from datetime import datetime, timezone

from wot_lot_bot.account import WotAccount
from wot_lot_bot.slides import fmt_int

MAX_CHARS = 3900  # Telegram caps a message at 4096
MAX_NAMES = 40


def _names(tanks) -> str:
    names = [t.name for t in tanks[:MAX_NAMES]]
    if len(tanks) > MAX_NAMES:
        names.append(f"и ещё {len(tanks) - MAX_NAMES}")
    return ", ".join(names)


def lot_text(account: WotAccount, now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    region = account.region_phrase or account.region
    lines = [f"World of Tanks{' · ' + region if region else ''}"]
    win = "" if account.win_percent is None else f" · Победы: {account.win_percent:.2f}%".replace(".", ",")
    lines.append(f"Бои: {fmt_int(account.battles)}{win}")
    lines.append(f"Золото: {fmt_int(account.gold)} · Кредиты: {fmt_int(account.credits)}")
    if account.has_premium(now):
        lines.append(f"Премиум: до {account.premium_until:%d.%m.%Y}")
    lines.append(f"Танков: {account.tank_count} · Топов X: {account.top_count} · "
                 f"Премов: {account.premium_count}")
    if account.tops:
        lines += ["", f"Топы X ({len(account.tops)}): {_names(account.tops)}"]
    if account.premiums:
        lines += ["", f"Премы ({len(account.premiums)}): {_names(account.premiums)}"]
    text = "\n".join(lines).replace(" ", " ")
    return text if len(text) <= MAX_CHARS else text[:MAX_CHARS - 1] + "…"
