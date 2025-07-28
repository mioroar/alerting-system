import asyncio

from config import logger
from db.init_db import init_db
from db.logic import get_pool, upsert_open_interest
from modules.oi.config import OI_CHECK_INTERVAL_SEC
from modules.oi.tracker.logic import fetch_oi_info


async def collect_oi_loop() -> None:
    """
    Бесконечный цикл опроса Binance и записи OI в БД.

    Выполняется в бесконечном цикле, опрашивает Binance каждые OI_CHECK_INTERVAL_SEC секунд.
    Полученные данные записываются в БД.

    Args:
        None
    """
    logger.info("Starting OI tracker loop")
    while True:
        try:
            oi_info = await fetch_oi_info()
            logger.info("Collected %d OI entries", len(oi_info))
            await upsert_open_interest(oi_info)
        except Exception as exc:
            logger.exception("Error in OI loop: %s", exc)
        await asyncio.sleep(OI_CHECK_INTERVAL_SEC)


async def main() -> None:
    """Точка входа сервиса.

    Инициализирует БД, запускает цикл сбора OI и завершает работу.
    """
    logger.info("Starting OI tracker service")
    await init_db()
    try:
        await collect_oi_loop()
    finally:
        pool = await get_pool()
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
