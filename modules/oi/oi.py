import asyncio

from config import logger
from db.logic import get_pool, upsert_open_interest
from modules.oi.config import OI_CHECK_INTERVAL_SEC
from modules.oi.tracker.logic import fetch_oi_info, get_blacklist_stats


async def collect_oi_loop() -> None:
    """Бесконечный цикл опроса Binance и записи OI в БД.

    Выполняется в бесконечном цикле, опрашивает Binance каждые OI_CHECK_INTERVAL_SEC секунд.
    Полученные данные записываются в БД.

    Returns:
        None

    Raises:
        Exception: При критических ошибках в цикле сбора данных.

    Note:
        - При ошибках увеличивает время ожидания экспоненциально
        - Максимум 5 последовательных ошибок перед длительной паузой
        - Каждые 10 итераций выводит статистику черного списка
        - Обеспечивает graceful handling ошибок без прерывания цикла
    """
    logger.info("Starting OI tracker loop")
    
    consecutive_errors = 0
    max_consecutive_errors = 5
    iteration = 0
    
    while True:
        iteration += 1
        
        try:
            oi_info = await fetch_oi_info()
            
            if oi_info:
                await upsert_open_interest(oi_info)
                logger.info("Collected %d OI entries", len(oi_info))
            else:
                logger.warning("No OI data collected in iteration %d", iteration)
            
            if iteration % 10 == 0:
                stats = get_blacklist_stats()
                if stats["blacklisted_count"] > 0:
                    logger.info("Blacklist stats: %d symbols blacklisted: %s", 
                               stats["blacklisted_count"], 
                               ", ".join(stats["blacklisted_symbols"][:5]))
            
            consecutive_errors = 0
            
        except Exception as exc:
            consecutive_errors += 1
            logger.exception("Error in OI loop (iteration %d, consecutive error #%d): %s", 
                           iteration, consecutive_errors, exc)
            
            if consecutive_errors >= max_consecutive_errors:
                logger.warning("Too many consecutive errors (%d), using extended sleep", 
                           consecutive_errors)
                await asyncio.sleep(OI_CHECK_INTERVAL_SEC * 3)
            else:
                await asyncio.sleep(min(OI_CHECK_INTERVAL_SEC * consecutive_errors, 300))
            continue
            
        await asyncio.sleep(OI_CHECK_INTERVAL_SEC)


async def main() -> None:
    """Точка входа сервиса.

    Инициализирует БД, запускает цикл сбора OI и завершает работу.

    Returns:
        None

    Raises:
        KeyboardInterrupt: При получении сигнала прерывания.
        Exception: При критических ошибках инициализации или в основном цикле.

    Note:
        Обеспечивает graceful shutdown с закрытием HTTP клиента и пула БД.
    """
    logger.info("Starting OI tracker service")
    
    try:
        await collect_oi_loop()
    except KeyboardInterrupt:
        logger.info("Received interrupt signal, shutting down...")
    except Exception as exc:
        logger.exception("Critical error in main: %s", exc)
    finally:
        try:
            from modules.oi.config import _CLIENT
            if _CLIENT is not None:
                await _CLIENT.aclose()
                logger.info("HTTP client closed")

            pool = await get_pool()
            if pool:
                await pool.close()
                logger.info("Database pool closed")
        except Exception as exc:
            logger.exception("Error during cleanup: %s", exc)


if __name__ == "__main__":
    asyncio.run(main())