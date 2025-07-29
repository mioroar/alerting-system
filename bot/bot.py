import asyncio
from contextlib import suppress

from bot.handlers.modules.composite import composite_loop
from bot.settings import dp, bot
from bot.handlers.another import another_router
from bot.handlers.standart import standart_router

dp.include_router(standart_router)
dp.include_router(another_router)

async def main() -> None:
    """Запускает Telegram бота для обработки пользовательских команд.
    
    Инициализирует и запускает Telegram бота с настроенными роутерами
    для обработки различных типов команд. Удаляет webhook перед запуском
    для избежания конфликтов.
    
    Returns:
        None
    """
    await bot.delete_webhook(drop_pending_updates=True)
    comp_task = asyncio.create_task(composite_loop())
    try:
        await dp.start_polling(bot)
    finally:
        comp_task.cancel()
        with suppress(asyncio.CancelledError):
            await comp_task

if __name__ == "__main__":
    asyncio.run(main())
