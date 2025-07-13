import asyncio

from bot.settings import dp, bot
from bot.handlers.another import another_router
from bot.handlers.standart import standart_router

dp.include_router(standart_router)
dp.include_router(another_router)

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
