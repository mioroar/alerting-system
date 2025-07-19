import asyncio
from config import logger
from db.init_db import init_db
from modules.volume_change.tracker.logic import run_volume_tracker

async def main() -> None:
    """Инициализация БД и запуск трекера объёмов."""
    logger.info("Starting volume tracker (WebSocket)")
    await init_db()
    await run_volume_tracker()

if __name__ == "__main__":
    asyncio.run(main())