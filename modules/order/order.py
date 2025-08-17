import asyncio

from config import logger
from db.logic import get_pool, close_pool
from modules.order.config import ORDER_TRACKER_BATCH_INTERVAL, SYMBOLS
from modules.order.tracker.logic import (
    fetch_futures_tickers,
    start_binance_listeners,
    update_tickers_task,
    save_densities_task,
    cleanup_task
)


async def collect_order_info_loop() -> None:
    """Цикл сбора данных о плотности ордеров с Binance и сохранения в базу данных.
    
    Запускает все необходимые фоновые задачи:
    - WebSocket слушатели для получения данных depth
    - Периодическое обновление списка тикеров
    - Сохранение данных в базу
    - Очистка устаревших данных
    """
    logger.info("[ORDER_MAIN] Starting order density tracker loop")
    
    try:
        # Получаем начальный список тикеров
        tickers = await fetch_futures_tickers()
        SYMBOLS.clear()
        SYMBOLS.extend(tickers)
        logger.info(f"[ORDER_MAIN] Загружено {len(SYMBOLS)} тикеров Binance Futures")
        
        # Запускаем все фоновые задачи
        tasks = []
        
        # WebSocket слушатели
        ws_tasks = await start_binance_listeners()
        tasks.extend(ws_tasks)
        
        # Периодические задачи
        tasks.append(asyncio.create_task(update_tickers_task()))
        tasks.append(asyncio.create_task(save_densities_task()))
        tasks.append(asyncio.create_task(cleanup_task()))
        
        logger.info(f"[ORDER_MAIN] Запущено {len(tasks)} фоновых задач")
        
        # Ждем завершения любой из задач (обычно не должно происходить)
        await asyncio.gather(*tasks, return_exceptions=True)
        
    except Exception as e:
        logger.exception(f"[ORDER_MAIN] Критическая ошибка в основном цикле: {e}")


async def main() -> None:
    """Точка входа для запуска трекера плотности ордеров.
    
    Инициализирует подключение к базе данных и запускает основной цикл.
    При завершении корректно закрывает pool соединений.
    """
    logger.info("[ORDER_MAIN] Starting order density tracker")
    
    try:
        # Проверяем подключение к БД
        pool = await get_pool()
        logger.info("[ORDER_MAIN] Database connection established")
        
        # Запускаем основной цикл
        await collect_order_info_loop()
        
    except Exception as e:
        logger.exception(f"[ORDER_MAIN] Error in main loop: {e}")
    finally:
        try:
            await close_pool()
            logger.info("[ORDER_MAIN] Database pool closed")
        except Exception as e:
            logger.error(f"[ORDER_MAIN] Error closing database pool: {e}")


if __name__ == "__main__":
    asyncio.run(main())