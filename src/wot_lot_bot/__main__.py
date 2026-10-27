from __future__ import annotations

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession

from wot_lot_bot.bot import build_router
from wot_lot_bot.config import get_settings
from wot_lot_bot.render import find_browser


async def run() -> None:
    settings = get_settings()
    if not settings.telegram_bot_token:
        sys.exit("TELEGRAM_BOT_TOKEN is empty")
    if not settings.admin_ids:
        sys.exit("ADMIN_TELEGRAM_IDS is empty: nobody could use the bot")
    if not settings.lolz_api_token:
        sys.exit("LOLZ_API_TOKEN is empty")
    browser = find_browser(settings.chromium_path)
    if browser:
        logging.info("Chromium: %s", browser[0])
    else:
        logging.error("Chromium not found: slides cannot be rendered until CHROMIUM_PATH is set")

    if settings.telegram_proxy:
        logging.info("Telegram proxy is enabled")
        bot = Bot(token=settings.telegram_bot_token, session=AiohttpSession(proxy=settings.telegram_proxy))
    else:
        bot = Bot(token=settings.telegram_bot_token)
    dp = Dispatcher()
    dp.include_router(build_router(settings, browser))
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    # httpx logs every request URL at INFO; tank picture URLs are noise.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    asyncio.run(run())


if __name__ == "__main__":
    main()
