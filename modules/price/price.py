import asyncio
from config import logger
from modules.price.config import PRICE_CHECK_INTERVAL_IN_SECONDS
from modules.price.tracker.logic import fetch_price_info

# TODO: В collect_price_info_loop сохранить в базу данных

async def collect_price_info_loop():
    """Цикл сбора цен с Binance и сохранения в базу данных."""
    logger.info("Starting price tracker loop")
    while True:
        try:
            price_info = await fetch_price_info()
            logger.info(f"Collected {len(price_info)} price info")
            # TODO: Сохранить в базу данных
        except Exception as e:
            logger.exception(f"Error collecting price info: {e}")
        finally:
            await asyncio.sleep(PRICE_CHECK_INTERVAL_IN_SECONDS)
            
async def main():
    """Точка входа для запуска цикла сбора цен."""
    logger.info("Starting price tracker")
    try:
        await collect_price_info_loop()
    except Exception as e:
        logger.exception(f"Error in main loop: {e}")

if __name__ == "__main__":
    asyncio.run(main())
