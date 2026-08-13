import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from dotenv import load_dotenv

import db
from handlers import AccessMiddleware, router


async def main():
    logging.basicConfig(level=logging.INFO)
    load_dotenv()

    token = os.getenv("BOT_TOKEN")
    if not token:
        raise SystemExit("BOT_TOKEN не задан (см. .env.example)")

    allowed_ids = {
        int(x) for x in os.getenv("ALLOWED_USER_IDS", "").split(",") if x.strip()
    }
    if not allowed_ids:
        raise SystemExit("ALLOWED_USER_IDS не задан — бот приватный (см. .env.example)")

    db.init_db()

    bot = Bot(token)
    dp = Dispatcher()
    dp.update.outer_middleware(AccessMiddleware(allowed_ids))
    dp.include_router(router)

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
