# import asyncio
# import json
# import time
# import websockets
# from typing import Dict, Tuple, Any, List, Set
# import httpx
# import datetime as dt

# from config import logger
# from db.logic import get_pool
# from modules.order.config import (
#     BINANCE_WS_URL,
#     FUTURES_EXCHANGE_INFO_URL,
#     MIN_ORDER_SIZE_USD,
#     MAX_PRICE_DEVIATION_PERCENT,
#     TICKER_CACHE,
#     SYMBOLS,
#     GROUP_SIZE,
#     ORDER_TRACKER_BATCH_INTERVAL,
#     WS_RECONNECT_INTERVAL,
#     OrderDensity,
#     OrderDensityRecord
# )
# from modules.config import TICKER_BLACKLIST

# # Глобальные структуры для отслеживания плотности ордеров
# # Ключ: (symbol, order_type, price), Значение: OrderDensity
# order_densities: Dict[Tuple[str, str, float], OrderDensity] = {}

# # Буфер для batch записи в БД
# pending_records: List[OrderDensityRecord] = []

# _SQL_ORDER_DENSITY = """
# INSERT INTO order_density (ts, symbol, order_type, price, size_usd, percent_from_market, first_seen, duration_sec)
# VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
# ON CONFLICT (ts, symbol, order_type, price) DO UPDATE
#     SET size_usd = EXCLUDED.size_usd,
#         percent_from_market = EXCLUDED.percent_from_market,
#         duration_sec = EXCLUDED.duration_sec;
# """


# async def fetch_futures_tickers() -> List[str]:
#     """Асинхронно получает список активных фьючерсных тикеров с Binance.

#     Фильтрует символы:
#       - статус "TRADING"
#       - исключает USDC пары

#     Returns:
#         List[str]: Список символов в нижнем регистре для формирования stream-имен.
    
#     Raises:
#         httpx.HTTPError: При ошибке HTTP запроса.
#     """
#     async with httpx.AsyncClient(timeout=10) as client:
#         response = await client.get(FUTURES_EXCHANGE_INFO_URL)
#         response.raise_for_status()
#         data = response.json()
#         tickers = []
#         for symbol_info in data.get("symbols", []):
#             symbol = symbol_info["symbol"]
#             if (symbol_info.get("status") == "TRADING" 
#                 and "usdc" not in symbol.lower()
#                 and not any(blacklisted.lower() in symbol.lower() for blacklisted in TICKER_BLACKLIST)):
#                 tickers.append(symbol.lower())
#         return tickers


# def calculate_price_percentage(price: float, reference_price: float) -> float:
#     """Вычисляет процентное отклонение цены от опорной.

#     Args:
#         price (float): Цена ордера.
#         reference_price (float): Опорная (рыночная) цена.

#     Returns:
#         float: Процентное отклонение: (price / reference_price − 1) * 100.
#     """
#     if reference_price == 0:
#         return 0.0
#     return ((price / reference_price) - 1) * 100


# def is_within_tracking_range(price: float, reference_price: float) -> bool:
#     """Проверяет, находится ли цена в диапазоне отслеживания (±10%).

#     Args:
#         price (float): Цена для проверки.
#         reference_price (float): Опорная цена.

#     Returns:
#         bool: True если цена в диапазоне ±10% от опорной.
#     """
#     if reference_price == 0:
#         return False
    
#     percent_deviation = abs(calculate_price_percentage(price, reference_price))
#     return percent_deviation <= MAX_PRICE_DEVIATION_PERCENT


# def process_order_level_for_tracking(
#     symbol: str,
#     order_type: str,
#     price: float,
#     quantity: float,
#     event_timestamp: int,
#     reference_price: float
# ) -> None:
#     """Обрабатывает уровень ордера для отслеживания плотности.

#     Обновляет или удаляет записи в order_densities на основе размера и времени.
#     Отслеживает только ордера больше MIN_ORDER_SIZE_USD в радиусе ±10%.

#     Args:
#         symbol (str): Символ торговой пары.
#         order_type (str): Тип ордера ("LONG" или "SHORT").
#         price (float): Цена уровня.
#         quantity (float): Количество в лотах.
#         event_timestamp (int): Временная метка события (ms).
#         reference_price (float): Опорная цена для расчета отклонения.
#     """
#     # Проверяем, что цена в диапазоне отслеживания
#     if not is_within_tracking_range(price, reference_price):
#         return

#     order_key = (symbol, order_type, price)
#     size_usd = price * quantity
#     current_time = int(time.time() * 1000)

#     # Удаляем уровень если количество <= 0 или размер < минимального
#     if quantity <= 0 or size_usd < MIN_ORDER_SIZE_USD:
#         if order_key in order_densities:
#             del order_densities[order_key]
#             logger.debug(f"[ORDER_TRACK] Удален уровень {order_key}: qty={quantity}, size_usd={size_usd}")
#         return

#     percent_from_market = calculate_price_percentage(price, reference_price)

#     # Обновляем или создаем запись
#     if order_key in order_densities:
#         order_densities[order_key].update({
#             "size_usd": size_usd,
#             "timestamp": current_time,
#             "percent_from_market": percent_from_market
#         })
#         logger.debug(f"[ORDER_TRACK] Обновлен {order_key}: size_usd={size_usd:.0f}, percent={percent_from_market:.2f}%")
#     else:
#         order_densities[order_key] = OrderDensity(
#             symbol=symbol,
#             order_type=order_type,
#             price=price,
#             size_usd=size_usd,
#             timestamp=current_time,
#             first_seen=current_time,
#             percent_from_market=percent_from_market
#         )
#         logger.debug(f"[ORDER_TRACK] Создан {order_key}: size_usd={size_usd:.0f}, percent={percent_from_market:.2f}%")


# def chunk_list(lst: List[str], n: int) -> List[List[str]]:
#     """Разбивает список на группы фиксированного размера.

#     Args:
#         lst (List[str]): Исходный список.
#         n (int): Размер каждой группы.

#     Returns:
#         List[List[str]]: Список групп размером до n элементов.
#     """
#     return [lst[i: i + n] for i in range(0, len(lst), n)]


# async def binance_listener_group(tickers_group: List[str]) -> None:
#     """Слушает WebSocket-потоки Binance для группы тикеров.

#     Подписывается на потоки depth и bookTicker.
#     Обрабатывает полученные сообщения, обновляет TICKER_CACHE и вызывает process_order_level_for_tracking.
#     При завершении 1 часа переподключается.

#     Args:
#         tickers_group (List[str]): Список тикеров для подписки.
#     """
#     while True:
#         depth_streams = [f"{symbol}@depth" for symbol in tickers_group]
#         ticker_streams = [f"{symbol}@bookTicker" for symbol in tickers_group]
#         all_streams = depth_streams + ticker_streams
#         streams = "/".join(all_streams)
#         url = f"{BINANCE_WS_URL}?streams={streams}"
        
#         logger.info(f"[ORDER_WS] Подключаемся для группы: {tickers_group[:3]}... ({len(tickers_group)} тикеров)")
        
#         try:
#             async with websockets.connect(url, ping_interval=20, ping_timeout=20) as ws:
#                 start_time = time.time()
#                 while True:
#                     if time.time() - start_time > WS_RECONNECT_INTERVAL:
#                         logger.info(f"[ORDER_WS] Группа {tickers_group[:3]}...: 1 час истёк, переподключаемся")
#                         break
                    
#                     try:
#                         data = await asyncio.wait_for(ws.recv(), timeout=5)
#                     except asyncio.TimeoutError:
#                         continue

#                     data_json = json.loads(data)
#                     if "data" not in data_json:
#                         continue

#                     stream_name = data_json.get("stream", "")
#                     event_data = data_json["data"]

#                     # Обработка события bookTicker
#                     if "bookTicker" in stream_name:
#                         symbol = event_data.get("s", "").lower()
#                         best_bid = float(event_data.get("b", 0))
#                         best_ask = float(event_data.get("a", 0))
#                         mid_price = (best_bid + best_ask) / 2
                        
#                         # Обновляем кэш с актуальной ценой
#                         TICKER_CACHE[symbol] = {
#                             "bid": best_bid,
#                             "ask": best_ask,
#                             "mid": mid_price,
#                             "timestamp": event_data.get("E")
#                         }
#                         continue

#                     # Обработка события depth
#                     symbol = event_data.get("s").lower()
#                     event_timestamp = event_data.get("E")
#                     bids = event_data.get("b", [])
#                     asks = event_data.get("a", [])

#                     # Получаем reference_price из кэша
#                     reference_price = None
#                     ticker_data = TICKER_CACHE.get(symbol)
#                     if ticker_data and (time.time() * 1000 - ticker_data["timestamp"]) < 60000:  # Не старше 1 минуты
#                         reference_price = ticker_data["mid"]
#                     else:
#                         # Запасной вариант, если нет данных в кэше
#                         if bids and asks:
#                             best_bid = float(bids[0][0])
#                             best_ask = float(asks[0][0])
#                             reference_price = (best_bid + best_ask) / 2
#                         elif bids:
#                             reference_price = float(bids[0][0])
#                         elif asks:
#                             reference_price = float(asks[0][0])

#                     if reference_price is None:
#                         logger.warning(f"[ORDER_WS] Пропускаем обработку для {symbol}: невозможно вычислить reference_price")
#                         continue

#                     # Обрабатываем уровни bid
#                     for bid in bids:
#                         price_str, qty_str = bid
#                         price = float(price_str)
#                         quantity = float(qty_str)
#                         process_order_level_for_tracking(
#                             symbol, "LONG", price, quantity, event_timestamp, reference_price
#                         )
                    
#                     # Обрабатываем уровни ask
#                     for ask in asks:
#                         price_str, qty_str = ask
#                         price = float(price_str)
#                         quantity = float(qty_str)
#                         process_order_level_for_tracking(
#                             symbol, "SHORT", price, quantity, event_timestamp, reference_price
#                         )

#         except Exception as e:
#             if "no close frame" in str(e).lower():
#                 logger.warning(f"[ORDER_WS] Группа {tickers_group[:3]}...: соединение закрыто без закрывающей рамки, переподключаемся...")
#             else:
#                 logger.error(f"[ORDER_WS] Ошибка в группе {tickers_group[:3]}...: {e}")
        
#         await asyncio.sleep(1)


# async def start_binance_listeners() -> List[asyncio.Task]:
#     """Запускает фоновые задачи для каждой группы тикеров.

#     Разбивает SYMBOLS на группы размером GROUP_SIZE и для каждой создаёт задачу binance_listener_group.

#     Returns:
#         List[asyncio.Task]: Список запущенных задач.
#     """
#     groups = chunk_list(SYMBOLS, GROUP_SIZE)
#     logger.info(f"[ORDER_WS] Запуск {len(groups)} websocket-соединений для групп тикеров")
    
#     tasks = []
#     for group in groups:
#         tasks.append(asyncio.create_task(binance_listener_group(group)))
#     return tasks


# async def save_order_densities_to_db() -> None:
#     """Сохраняет накопленные данные о плотности ордеров в базу данных.

#     Создаёт записи OrderDensityRecord из текущих order_densities
#     и выполняет batch upsert в таблицу order_density.
#     """
#     if not order_densities:
#         return

#     current_time = int(time.time() * 1000)
#     records = []
    
#     for (symbol, order_type, price), density in order_densities.items():
#         duration_sec = (current_time - density["first_seen"]) // 1000
        
#         record = OrderDensityRecord(
#             symbol=symbol,
#             order_type=order_type,
#             price=price,
#             size_usd=density["size_usd"],
#             percent_from_market=density["percent_from_market"],
#             first_seen=density["first_seen"],
#             duration_sec=max(0, duration_sec)
#         )
#         records.append(record)

#     if records:
#         try:
#             pool = await get_pool()
#             rows = [
#                 (
#                     dt.datetime.fromtimestamp(current_time / 1000, tz=dt.timezone.utc),
#                     record["symbol"],
#                     record["order_type"],
#                     record["price"],
#                     record["size_usd"],
#                     record["percent_from_market"],
#                     dt.datetime.fromtimestamp(record["first_seen"] / 1000, tz=dt.timezone.utc),
#                     record["duration_sec"]
#                 )
#                 for record in records
#             ]
            
#             async with pool.acquire() as conn:
#                 await conn.executemany(_SQL_ORDER_DENSITY, rows)
            
#             logger.info(f"[ORDER_DB] Сохранено {len(records)} записей плотности ордеров")
            
#         except Exception as e:
#             logger.error(f"[ORDER_DB] Ошибка при сохранении данных: {e}")


# async def update_tickers_task() -> None:
#     """Периодически обновляет список тикеров каждый час.

#     Вызывает fetch_futures_tickers, очищает и заполняет SYMBOLS.
#     """
#     while True:
#         try:
#             await asyncio.sleep(3600)
#             tickers = await fetch_futures_tickers()
#             SYMBOLS.clear()
#             SYMBOLS.extend(tickers)
#             logger.info(f"[ORDER_TICKERS] Обновлён список тикеров Binance Futures: {len(SYMBOLS)} символов")
#         except Exception as e:
#             logger.error(f"[ORDER_TICKERS] Ошибка при обновлении тикеров: {e}")
#             await asyncio.sleep(60)


# async def save_densities_task() -> None:
#     """Периодически сохраняет данные о плотности ордеров в базу данных.

#     Вызывает save_order_densities_to_db каждые ORDER_TRACKER_BATCH_INTERVAL секунд.
#     """
#     while True:
#         try:
#             await asyncio.sleep(ORDER_TRACKER_BATCH_INTERVAL)
#             await save_order_densities_to_db()
#         except Exception as e:
#             logger.error(f"[ORDER_DB] Ошибка при сохранении плотностей: {e}")
#             await asyncio.sleep(ORDER_TRACKER_BATCH_INTERVAL)


# async def cleanup_old_densities() -> None:
#     """Очищает устаревшие записи из памяти.

#     Удаляет записи order_densities старше 1 часа для предотвращения
#     неконтролируемого роста памяти.
#     """
#     current_time = int(time.time() * 1000)
#     max_age_ms = 3600 * 1000  # 1 час
    
#     keys_to_remove = []
#     for key, density in order_densities.items():
#         if current_time - density["timestamp"] > max_age_ms:
#             keys_to_remove.append(key)
    
#     for key in keys_to_remove:
#         del order_densities[key]
    
#     if keys_to_remove:
#         logger.info(f"[ORDER_CLEANUP] Удалено {len(keys_to_remove)} устаревших записей из памяти")


# async def cleanup_task() -> None:
#     """Периодически очищает старые данные каждые 30 минут."""
#     while True:
#         try:
#             await asyncio.sleep(1800)  # 30 минут
#             await cleanup_old_densities()
#         except Exception as e:
#             logger.error(f"[ORDER_CLEANUP] Ошибка при очистке данных: {e}")
#             await asyncio.sleep(60)