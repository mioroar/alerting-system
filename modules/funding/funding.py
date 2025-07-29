import asyncio
import datetime as dt

from config import logger
from db.init_db import init_db
from db.logic import get_pool, upsert_funding_rates
from modules.funding.config import FUNDING_CHECK_INTERVAL_SEC
from modules.funding.tracker.logic import fetch_funding_info


async def collect_funding_loop() -> None:
    """Бесконечно: fetch → upsert → sleep.

    Основной цикл сбора данных о funding ставках с Binance API.
    Обрабатывает ошибки с экспоненциальной задержкой.

    Returns:
        None

    Raises:
        Exception: При критических ошибках в цикле сбора данных.

    Note:
        - При ошибках увеличивает время ожидания экспоненциально
        - Максимум 5 последовательных ошибок перед длительной паузой
        - Обрабатывает ошибки обработки отдельных элементов данных
    """
    logger.info("Starting funding tracker loop")
    consecutive_errors = 0
    max_consecutive_errors = 5
    
    while True:
        try:
            data = await fetch_funding_info()
            
            if not data:
                logger.warning("No funding data received")
                await asyncio.sleep(FUNDING_CHECK_INTERVAL_SEC)
                continue
            
            rows = []
            for item in data:
                try:
                    rows.append((
                        dt.datetime.fromtimestamp(item["time"] / 1000, tz=dt.timezone.utc),
                        item["symbol"],
                        item["rate"],
                        dt.datetime.fromtimestamp(item["next_funding_ts"] / 1000, tz=dt.timezone.utc),
                    ))
                except (KeyError, ValueError, OSError) as e:
                    logger.warning("Error processing funding item %s: %s", item, e)
                    continue
            
            if rows:
                await upsert_funding_rates(rows)
                logger.debug("Upserted %d funding rows", len(rows))
            
            consecutive_errors = 0
            
        except Exception as exc:
            consecutive_errors += 1
            logger.exception("Funding loop error (#%d): %s", consecutive_errors, exc)
            
            if consecutive_errors >= max_consecutive_errors:
                logger.error("Too many consecutive errors (%d), sleeping longer", consecutive_errors)
                await asyncio.sleep(FUNDING_CHECK_INTERVAL_SEC * 5)
            else:
                await asyncio.sleep(min(FUNDING_CHECK_INTERVAL_SEC * consecutive_errors, 300))
            continue
            
        await asyncio.sleep(FUNDING_CHECK_INTERVAL_SEC)


async def main() -> None:
    """Запуск сервиса сбора funding данных.

    Инициализирует базу данных и запускает основной цикл сбора данных.
    Обеспечивает корректное закрытие соединений при завершении.

    Returns:
        None

    Raises:
        Exception: При ошибках инициализации БД или критических ошибках в цикле.

    Note:
        Обеспечивает graceful shutdown с закрытием пула соединений.
    """
    await init_db()
    pool = None
    try:
        await collect_funding_loop()
    finally:
        try:
            pool = await get_pool()
            if pool:
                await pool.close()
        except Exception as e:
            logger.error("Error closing pool: %s", e)


if __name__ == "__main__":
    asyncio.run(main())
