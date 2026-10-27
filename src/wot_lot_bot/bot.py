"""Telegram side: a lot link in, slides (as files) and a lot summary out.

Only ADMIN_TELEGRAM_IDS are served; anyone else gets no reply at all.
Slides go as documents so Telegram does not recompress them.
"""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandStart
from aiogram.types import BufferedInputFile, InputMediaDocument, Message

from wot_lot_bot.account import NotWotItem, from_item
from wot_lot_bot.config import Settings
from wot_lot_bot.images import tank_images
from wot_lot_bot.lolz import LolzClient, LolzError, parse_item_id
from wot_lot_bot.render import RenderError, render
from wot_lot_bot.slides import build_slides
from wot_lot_bot.summary import lot_text

logger = logging.getLogger(__name__)

ALBUM_LIMIT = 10
HELP = (
    "Пришли ссылку на лот World of Tanks с Lolz, например\n"
    "https://lzt.market/123456789/\n"
    "или просто ID лота. В ответ придут картинки 1280×720 для PayGame "
    "и текст со статой для описания."
)


async def _status(message: Message, text: str) -> None:
    try:
        await message.edit_text(text)
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


def build_router(settings: Settings, browser: list[str] | None) -> Router:
    router = Router(name="wot_lot")
    router.message.filter(F.from_user.id.in_(settings.admin_ids))
    busy: set[int] = set()

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
        user_id = message.from_user.id
        if user_id in busy:
            await message.answer("⏳ Предыдущий лот ещё собирается, дождись его.")
            return
        busy.add(user_id)
        status = await message.answer("⏳ Забираю лот с Lolz…")
        try:
            async with LolzClient(settings.lolz_api_token, settings.lolz_api_base) as client:
                item = await client.get_item(item_id)
            account = from_item(item)
            del item  # may hold login data; only `account` goes further

            await _status(status, f"🖼 Качаю картинки танков: {len(account.tanks)}…")
            images = await tank_images(account.tanks, settings.tank_cache_dir)
            slides = build_slides(account, images, watermark=settings.watermark)
            files = []
            for number, slide in enumerate(slides, 1):
                await _status(status, f"🎨 Рисую слайды: {number}/{len(slides)}")
                files.append((slide.name, await render(slide.html, browser=browser)))

            await _status(status, "📤 Отправляю…")
            await _send_files(message, files)
            missing = len(account.tanks) - len(images)
            text = lot_text(account)
            if missing:
                text += f"\n\n⚠️ Не скачались картинки {missing} танков: на слайдах силуэт."
            await message.answer(text)
            try:
                await status.delete()
            except TelegramBadRequest:
                pass
        except (LolzError, NotWotItem, RenderError) as exc:
            await _status(status, f"❌ {exc}")
        except Exception:
            logger.exception("Lot %s failed", item_id)
            await _status(status, "❌ Не получилось собрать лот, подробности в логах бота.")
        finally:
            busy.discard(user_id)

    return router
