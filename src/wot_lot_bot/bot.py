"""Telegram side: a lot link in, slides (as files) and a lot summary out.

Only ADMIN_TELEGRAM_IDS are served; anyone else gets no reply at all.
Slides go as documents so Telegram does not recompress them.

A Lolz item may hold a World of Tanks and a Tanks Blitz account at once. Then
the bot asks which game the slides are for; the answer button carries only
the game and the item ID, and the item is fetched again, so no item data
waits in memory between the two steps.
"""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandStart
from aiogram.types import (BufferedInputFile, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup,
                           InputMediaDocument, Message)

from wot_lot_bot.account import BLITZ, GAMES, WOT, NotWotItem, WotAccount, from_item, games
from wot_lot_bot.config import Settings
from wot_lot_bot.images import tank_images
from wot_lot_bot.lolz import LolzClient, LolzError, parse_item_id
from wot_lot_bot.render import RenderError, render
from wot_lot_bot.slides import build_slides, fmt_int
from wot_lot_bot.summary import lot_text

logger = logging.getLogger(__name__)

ALBUM_LIMIT = 10
BOTH = "both"
CALLBACK_PREFIX = "lot"
HELP = (
    "Пришли ссылку на лот World of Tanks или Tanks Blitz с Lolz, например\n"
    "https://lzt.market/123456789/\n"
    "или просто ID лота. В ответ придут картинки 1280×720 для PayGame "
    "и текст со статой для описания. Если в лоте аккаунты сразу в двух играх, "
    "бот спросит, под какую делать картинки."
)


async def _status(message: Message, text: str, markup: InlineKeyboardMarkup | None = None) -> None:
    try:
        await message.edit_text(text, reply_markup=markup)
    except TelegramBadRequest:
        pass  # same text or message gone: progress is cosmetic


async def _send_files(message: Message, files: list[tuple[str, bytes]]) -> None:
    for start in range(0, len(files), ALBUM_LIMIT):
        batch = files[start:start + ALBUM_LIMIT]
        if len(batch) == 1:
            name, data = batch[0]
            await message.answer_document(BufferedInputFile(data, filename=name))
            continue
        await message.answer_media_group([
            InputMediaDocument(media=BufferedInputFile(data, filename=name)) for name, data in batch
        ])


def _callback_data(choice: str, item_id: int) -> str:
    return f"{CALLBACK_PREFIX}:{choice}:{item_id}"


def parse_callback(data: str) -> tuple[tuple[str, ...], int] | None:
    """Games and item ID from a choice button, or None for anything else."""
    parts = (data or "").split(":")
    if len(parts) != 3 or parts[0] != CALLBACK_PREFIX or not parts[2].isdigit():
        return None
    choice, item_id = parts[1], int(parts[2])
    if choice == BOTH:
        return GAMES, item_id
    if choice in GAMES:
        return (choice,), item_id
    return None


def _line(account: WotAccount) -> str:
    return (f"• {account.game_title}: {fmt_int(account.battles)} боёв, "
            f"танков {account.tank_count}, топов X {account.top_count}, премов {account.premium_count}")


def choice_prompt(accounts: list[WotAccount], item_id: int) -> tuple[str, InlineKeyboardMarkup]:
    """Question and buttons for an item with accounts in both games."""
    text = "\n".join(["В лоте аккаунты в двух играх:", *map(_line, accounts),
                      "", "Под какую игру делать картинки?"])
    titles = {account.game: account.game_title for account in accounts}
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=titles[game], callback_data=_callback_data(game, item_id))
         for game in (WOT, BLITZ)],
        [InlineKeyboardButton(text="Обе игры", callback_data=_callback_data(BOTH, item_id))],
    ])
    return text, markup


def build_router(settings: Settings, browser: list[str] | None) -> Router:
    router = Router(name="wot_lot")
    router.message.filter(F.from_user.id.in_(settings.admin_ids))
    router.callback_query.filter(F.from_user.id.in_(settings.admin_ids))
    busy: set[int] = set()

    async def fetch(item_id: int) -> tuple[list[WotAccount], tuple[str, ...]]:
        async with LolzClient(settings.lolz_api_token, settings.lolz_api_base) as client:
            item = await client.get_item(item_id)
        found = games(item)
        accounts = [from_item(item, game) for game in found]
        del item  # may hold login data; only `accounts` go further
        return accounts, found

    async def make(chat: Message, status: Message, accounts: list[WotAccount]) -> None:
        for account in accounts:
            game = f" {account.game_title}" if len(accounts) > 1 else ""
            await _status(status, f"🖼 Качаю картинки танков{game}: {len(account.tanks)}…")
            images = await tank_images(account.tanks, settings.tank_cache_dir)
            slides = build_slides(account, images, watermark=settings.watermark)
            files = []
            for number, slide in enumerate(slides, 1):
                await _status(status, f"🎨 Рисую слайды{game}: {number}/{len(slides)}")
                files.append((slide.name, await render(slide.html, browser=browser)))

            await _status(status, "📤 Отправляю…")
            await _send_files(chat, files)
            missing = len(account.tanks) - len(images)
            text = lot_text(account)
            if missing:
                text += f"\n\n⚠️ Не скачались картинки {missing} танков: на слайдах силуэт."
            await chat.answer(text)
        try:
            await status.delete()
        except TelegramBadRequest:
            pass

    async def run(user_id: int, item_id: int, chat: Message, status: Message,
                  wanted: tuple[str, ...] | None) -> None:
        """Fetch the item and make slides for `wanted` games; None asks when there are two."""
        busy.add(user_id)
        try:
            await _status(status, "⏳ Забираю лот с Lolz…")
            accounts, found = await fetch(item_id)
            if wanted is None and len(found) > 1:
                text, markup = choice_prompt(accounts, item_id)
                await _status(status, text, markup)
                return
            if wanted is not None:
                accounts = [account for account in accounts if account.game in wanted]
                if not accounts:
                    await _status(status, "❌ В лоте нет аккаунта в этой игре.")
                    return
            await make(chat, status, accounts)
        except (LolzError, NotWotItem, RenderError) as exc:
            await _status(status, f"❌ {exc}")
        except Exception:
            logger.exception("Lot %s failed", item_id)
            await _status(status, "❌ Не получилось собрать лот, подробности в логах бота.")
        finally:
            busy.discard(user_id)

    @router.message(CommandStart())
    async def start(message: Message) -> None:
        await message.answer(HELP)

    @router.message(F.text)
    async def lot(message: Message) -> None:
        item_id = parse_item_id(message.text or "")
        if not item_id:
            await message.answer(HELP)
            return
        if not browser:
            await message.answer("❌ Не найден Chromium/Chrome: задай CHROMIUM_PATH в .env.")
            return
        if message.from_user.id in busy:
            await message.answer("⏳ Предыдущий лот ещё собирается, дождись его.")
            return
        busy.add(message.from_user.id)  # before the first await: one lot at a time
        try:
            status = await message.answer("⏳ Забираю лот с Lolz…")
        except Exception:
            busy.discard(message.from_user.id)
            raise
        await run(message.from_user.id, item_id, message, status, None)

    @router.callback_query(F.data.startswith(f"{CALLBACK_PREFIX}:"))
    async def choose(callback: CallbackQuery) -> None:
        parsed = parse_callback(callback.data or "")
        status = callback.message
        if not parsed or not isinstance(status, Message):
            await callback.answer("Кнопка устарела, пришли ссылку ещё раз.")
            return
        if callback.from_user.id in busy:
            await callback.answer("⏳ Предыдущий лот ещё собирается.")
            return
        busy.add(callback.from_user.id)
        try:
            await callback.answer()
        except TelegramBadRequest:
            pass  # the query is too old to answer; the work still runs
        wanted, item_id = parsed
        await run(callback.from_user.id, item_id, status, status, wanted)

    return router
