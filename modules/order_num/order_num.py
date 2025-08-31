import asyncio
import datetime as dt

from config import logger
from db.logic import get_pool
from modules.order_num.config import ORDER_NUM_CHECK_INTERVAL_SEC
from modules.order_num.tracker.logic import (
    fetch_trade_counts_from_klines,
    fetch_historical_trade_counts,
    close_client
)


async def upsert_trade_counts(trade_counts: list) -> None:
    """Сохраняет количество сделок в БД.
    
    Args:
        trade_counts: Список TradeCountInfo словарей.
    """
    if not trade_counts:
        return
    
    pool = await get_pool()
    
    rows = [
        (
            dt.datetime.fromtimestamp(tc["time"] / 1000, tz=dt.timezone.utc),
            tc["symbol"],
            tc["trade_count"]
        )
        for tc in trade_counts
    ]
    
    async with pool.acquire() as conn:
        await conn.executemany(
            """
            INSERT INTO trade_count (ts, symbol, trade_count)
            VALUES ($1, $2, $3)
            ON CONFLICT (ts, symbol) DO UPDATE
                SET trade_count = EXCLUDED.trade_count;
            """,
            rows
        )
    
    logger.debug("Inserted %d trade count records", len(rows))


async def collect_order_num_loop() -> None:
    """Бесконечный цикл сбора данных о количестве сделок.
    
    Опрашивает Binance API каждые ORDER_NUM_CHECK_INTERVAL_SEC секунд
    и сохраняет данные в БД.
    """
    logger.info("Starting order_num tracker loop")
    
    # При первом запуске загружаем исторические данные
    first_run = True
    consecutive_errors = 0
    max_consecutive_errors = 5
    iteration = 0
    
    while True:
        iteration += 1
        
        try:
            if first_run:
                # Загружаем историю за последние 20 минут при первом запуске
                logger.info("Loading historical trade count data...")
                historical_data = await fetch_historical_trade_counts(minutes_back=20)
                if historical_data:
                    await upsert_trade_counts(historical_data)
                    logger.info("Loaded %d historical records", len(historical_data))
                first_run = False
                await asyncio.sleep(5)  # Пауза после загрузки истории
            
            # Собираем текущие данные из свечей
            trade_counts = await fetch_trade_counts_from_klines()
            
            if trade_counts:
                await upsert_trade_counts(trade_counts)
                logger.info("Collected trade counts for %d symbols", len(trade_counts))
            else:
                logger.warning("No trade count data collected in iteration %d", iteration)
            
            consecutive_errors = 0
            
        except Exception as exc:
            consecutive_errors += 1
            logger.exception("Error in order_num loop (iteration %d, error #%d): %s", 
                           iteration, consecutive_errors, exc)
            
            if consecutive_errors >= max_consecutive_errors:
                logger.warning("Too many consecutive errors (%d), using extended sleep", 
                             consecutive_errors)
                await asyncio.sleep(ORDER_NUM_CHECK_INTERVAL_SEC * 3)
            else:
                await asyncio.sleep(min(ORDER_NUM_CHECK_INTERVAL_SEC * consecutive_errors, 300))
            continue
            
        await asyncio.sleep(ORDER_NUM_CHECK_INTERVAL_SEC)


async def main() -> None:
    """Точка входа сервиса order_num.
    
    Инициализирует БД и запускает цикл сбора данных.
    """
    logger.info("Starting order_num tracker service")
    
    try:
        await collect_order_num_loop()
    except KeyboardInterrupt:
        logger.info("Received interrupt signal, shutting down...")
    except Exception as exc:
        logger.exception("Critical error in main: %s", exc)
    finally:
        try:
            await close_client()
            logger.info("HTTP client closed")
            
            pool = await get_pool()
            if pool:
                await pool.close()
                logger.info("Database pool closed")
        except Exception as exc:
            logger.exception("Error during cleanup: %s", exc)


if __name__ == "__main__":
    asyncio.run(main())