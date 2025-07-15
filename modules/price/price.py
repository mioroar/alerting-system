import asyncio
from config import logger
from modules.price.config import PRICE_CHECK_INTERVAL_IN_SECONDS
from modules.price.tracker.logic import fetch_price_info
from db.logic import upsert_prices, get_pool
from db.init_db import init_db

async def collect_price_info_loop() -> None:
    """Цикл сбора цен с Binance и сохранения в базу данных."""
    logger.info("Starting price tracker loop")
    while True:
        try:
            price_info = await fetch_price_info()
            logger.info(f"Collected {len(price_info)} price info")
            print(f"Collected {len(price_info)} price info")
            await upsert_prices(price_info)
        except Exception as e:
            logger.exception(f"Error collecting price info: {e}")
        finally:
            await asyncio.sleep(PRICE_CHECK_INTERVAL_IN_SECONDS)
            
async def main() -> None:
    """Точка входа для запуска цикла сбора цен."""
    logger.info("Starting price tracker")
    await init_db()
    try:
        await collect_price_info_loop()
    except Exception as e:
        logger.exception(f"Error in main loop: {e}")
    finally:
        pool = await get_pool()
        await pool.close()

if __name__ == "__main__":
    asyncio.run(main())
