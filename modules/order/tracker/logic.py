import asyncio
import json
import time
import websockets
from typing import Dict, Tuple, Any, List, Set
import httpx
import datetime as dt

from config import logger
from db.logic import get_pool
from modules.order.config import (
    BINANCE_WS_URL,
    FUTURES_EXCHANGE_INFO_URL,
    MIN_ORDER_SIZE_USD,
    MAX_PRICE_DEVIATION_PERCENT,
    TICKER_CACHE,
    SYMBOLS,
    GROUP_SIZE,
    ORDER_TRACKER_BATCH_INTERVAL,
    WS_RECONNECT_INTERVAL,
    OrderDensity,
    DensityDBOperation
)
from modules.config import TICKER_BLACKLIST

# Глобальные структуры для отслеживания плотности ордеров
# Ключ: (symbol, price), Значение: OrderDensity
order_densities: Dict[Tuple[str, float], OrderDensity] = {}

# Буфер операций для БД
pending_db_operations: List[DensityDBOperation] = []

# SQL запросы
_SQL_INSERT_DENSITY = """
INSERT INTO order_density (
    ts, symbol, order_type, price, 
    current_size_usd, max_size_usd, 
    touched, reduction_usd,
    percent_from_market, first_seen, 
    last_updated, duration_sec
)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
ON CONFLICT (symbol, price) DO NOTHING;
"""

_SQL_UPDATE_DENSITY = """
UPDATE order_density 
SET 
    ts = $1,
    current_size_usd = $2,
    max_size_usd = $3,
    touched = $4,
    reduction_usd = $5,
    percent_from_market = $6,
    last_updated = $7,
    duration_sec = $8
WHERE symbol = $9 AND price = $10;
"""

_SQL_DELETE_DENSITY = """
DELETE FROM order_density 
WHERE symbol = $1 AND price = $2;
"""


async def fetch_futures_tickers() -> List[str]:
    """Асинхронно получает список активных фьючерсных тикеров с Binance.

    Фильтрует символы:
      - статус "TRADING"
      - исключает USDC пары
      - исключает тикеры из blacklist

    Returns:
        List[str]: Список символов в нижнем регистре для формирования stream-имен.
    
    Raises:
        httpx.HTTPError: При ошибке HTTP запроса.
    """
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(FUTURES_EXCHANGE_INFO_URL)
        response.raise_for_status()
        data = response.json()
        tickers = []
        for symbol_info in data.get("symbols", []):
            symbol = symbol_info["symbol"]
            if (symbol_info.get("status") == "TRADING" 
                and "usdc" not in symbol.lower()
                and not any(blacklisted.lower() in symbol.lower() for blacklisted in TICKER_BLACKLIST)):
                tickers.append(symbol.lower())
        return tickers


def calculate_price_percentage(price: float, reference_price: float) -> float:
    """Вычисляет процентное отклонение цены от опорной.

    Args:
        price (float): Цена ордера.
        reference_price (float): Опорная (рыночная) цена.

    Returns:
        float: Процентное отклонение: (price / reference_price − 1) * 100.
    """
    if reference_price == 0:
        return 0.0
    return ((price / reference_price) - 1) * 100


def is_within_tracking_range(price: float, reference_price: float) -> bool:
    """Проверяет, находится ли цена в диапазоне отслеживания (±10%).

    Args:
        price (float): Цена для проверки.
        reference_price (float): Опорная цена.

    Returns:
        bool: True если цена в диапазоне ±10% от опорной.
    """
    if reference_price == 0:
        return False
    
    percent_deviation = abs(calculate_price_percentage(price, reference_price))
    return percent_deviation <= MAX_PRICE_DEVIATION_PERCENT


def process_order_level_for_tracking(
    symbol: str,
    order_type: str,
    price: float,
    quantity: float,
    event_timestamp: int,
    reference_price: float
) -> None:
    """Обрабатывает уровень ордера для отслеживания плотности.

    Обновляет order_densities и создаёт операции для БД.
    Отслеживает только ордера больше MIN_ORDER_SIZE_USD в радиусе ±10%.

    Args:
        symbol (str): Символ торговой пары.
        order_type (str): Тип ордера ("LONG" или "SHORT").
        price (float): Цена уровня.
        quantity (float): Количество в лотах.
        event_timestamp (int): Временная метка события (ms).
        reference_price (float): Опорная цена для расчета отклонения.
    """
    # Проверяем, что цена в диапазоне отслеживания
    if not is_within_tracking_range(price, reference_price):
        return

    density_key = (symbol, price)
    size_usd = price * quantity
    current_time = int(time.time() * 1000)
    percent_from_market = calculate_price_percentage(price, reference_price)

    # Если размер меньше минимального или quantity <= 0 - удаляем плотность
    if quantity <= 0 or size_usd < MIN_ORDER_SIZE_USD:
        if density_key in order_densities:
            # Создаём операцию удаления
            pending_db_operations.append(DensityDBOperation(
                operation="DELETE",
                data=None,
                key=density_key
            ))
            del order_densities[density_key]
            logger.debug(f"[ORDER_TRACK] Удален уровень {density_key}: qty={quantity}, size_usd={size_usd}")
        return

    # Обновляем или создаем запись
    if density_key in order_densities:
        # Обновляем существующую плотность
        density = order_densities[density_key]
        old_size = density["current_size_usd"]
        
        # Обновляем максимальный размер
        max_size = max(density["max_size_usd"], size_usd)
        
        # Определяем, была ли плотность тронута
        touched = size_usd < max_size
        reduction_usd = max_size - size_usd if touched else 0.0
        
        density.update({
            "current_size_usd": size_usd,
            "max_size_usd": max_size,
            "touched": touched,
            "reduction_usd": reduction_usd,
            "percent_from_market": percent_from_market,
            "last_updated": current_time,
            "is_new": False
        })
        
        # Создаём операцию обновления
        pending_db_operations.append(DensityDBOperation(
            operation="UPDATE",
            data=density.copy(),
            key=density_key
        ))
        
        logger.debug(f"[ORDER_TRACK] Обновлен {density_key}: size={size_usd:.0f}, max={max_size:.0f}, touched={touched}")
    else:
        # Создаем новую запись
        density = OrderDensity(
            symbol=symbol,
            order_type=order_type,
            price=price,
            current_size_usd=size_usd,
            max_size_usd=size_usd,
            touched=False,
            reduction_usd=0.0,
            percent_from_market=percent_from_market,
            first_seen=current_time,
            last_updated=current_time,
            is_new=True
        )
        order_densities[density_key] = density
        
        # Создаём операцию вставки
        pending_db_operations.append(DensityDBOperation(
            operation="INSERT",
            data=density.copy(),
            key=density_key
        ))
        
        logger.debug(f"[ORDER_TRACK] Создан {density_key}: size={size_usd:.0f}, percent={percent_from_market:.2f}%")


def chunk_list(lst: List[str], n: int) -> List[List[str]]:
    """Разбивает список на группы фиксированного размера.

    Args:
        lst (List[str]): Исходный список.
        n (int): Размер каждой группы.

    Returns:
        List[List[str]]: Список групп размером до n элементов.
    """
    return [lst[i: i + n] for i in range(0, len(lst), n)]


async def binance_listener_group(tickers_group: List[str]) -> None:
    """Слушает WebSocket-потоки Binance для группы тикеров.

    Подписывается на потоки depth и bookTicker.
    Обрабатывает полученные сообщения, обновляет TICKER_CACHE и вызывает process_order_level_for_tracking.
    При завершении 1 часа переподключается.

    Args:
        tickers_group (List[str]): Список тикеров для подписки.
    """
    while True:
        depth_streams = [f"{symbol}@depth" for symbol in tickers_group]
        ticker_streams = [f"{symbol}@bookTicker" for symbol in tickers_group]
        all_streams = depth_streams + ticker_streams
        streams = "/".join(all_streams)
        url = f"{BINANCE_WS_URL}?streams={streams}"
        
        logger.info(f"[ORDER_WS] Подключаемся для группы: {tickers_group[:3]}... ({len(tickers_group)} тикеров)")
        
        try:
            async with websockets.connect(url, ping_interval=20, ping_timeout=20) as ws:
                start_time = time.time()
                while True:
                    if time.time() - start_time > WS_RECONNECT_INTERVAL:
                        logger.info(f"[ORDER_WS] Группа {tickers_group[:3]}...: 1 час истёк, переподключаемся")
                        break
                    
                    try:
                        data = await asyncio.wait_for(ws.recv(), timeout=5)
                    except asyncio.TimeoutError:
                        continue

                    data_json = json.loads(data)
                    if "data" not in data_json:
                        continue

                    stream_name = data_json.get("stream", "")
                    event_data = data_json["data"]

                    # Обработка события bookTicker
                    if "bookTicker" in stream_name:
                        symbol = event_data.get("s", "").lower()
                        best_bid = float(event_data.get("b", 0))
                        best_ask = float(event_data.get("a", 0))
                        mid_price = (best_bid + best_ask) / 2
                        
                        # Обновляем кэш с актуальной ценой
                        TICKER_CACHE[symbol] = {
                            "bid": best_bid,
                            "ask": best_ask,
                            "mid": mid_price,
                            "timestamp": event_data.get("E")
                        }
                        continue

                    # Обработка события depth
                    symbol = event_data.get("s").lower()
                    event_timestamp = event_data.get("E")
                    bids = event_data.get("b", [])
                    asks = event_data.get("a", [])

                    # Получаем reference_price из кэша
                    reference_price = None
                    ticker_data = TICKER_CACHE.get(symbol)
                    if ticker_data and (time.time() * 1000 - ticker_data["timestamp"]) < 60000:  # Не старше 1 минуты
                        reference_price = ticker_data["mid"]
                    else:
                        # Запасной вариант, если нет данных в кэше
                        if bids and asks:
                            best_bid = float(bids[0][0])
                            best_ask = float(asks[0][0])
                            reference_price = (best_bid + best_ask) / 2
                        elif bids:
                            reference_price = float(bids[0][0])
                        elif asks:
                            reference_price = float(asks[0][0])

                    if reference_price is None:
                        logger.warning(f"[ORDER_WS] Пропускаем обработку для {symbol}: невозможно вычислить reference_price")
                        continue

                    # Обрабатываем уровни bid
                    for bid in bids:
                        price_str, qty_str = bid
                        price = float(price_str)
                        quantity = float(qty_str)
                        process_order_level_for_tracking(
                            symbol, "LONG", price, quantity, event_timestamp, reference_price
                        )
                    
                    # Обрабатываем уровни ask
                    for ask in asks:
                        price_str, qty_str = ask
                        price = float(price_str)
                        quantity = float(qty_str)
                        process_order_level_for_tracking(
                            symbol, "SHORT", price, quantity, event_timestamp, reference_price
                        )

        except Exception as e:
            if "no close frame" in str(e).lower():
                logger.warning(f"[ORDER_WS] Группа {tickers_group[:3]}...: соединение закрыто без закрывающей рамки, переподключаемся...")
            else:
                logger.error(f"[ORDER_WS] Ошибка в группе {tickers_group[:3]}...: {e}")
        
        await asyncio.sleep(1)


async def start_binance_listeners() -> List[asyncio.Task]:
    """Запускает фоновые задачи для каждой группы тикеров.

    Разбивает SYMBOLS на группы размером GROUP_SIZE и для каждой создаёт задачу binance_listener_group.

    Returns:
        List[asyncio.Task]: Список запущенных задач.
    """
    groups = chunk_list(SYMBOLS, GROUP_SIZE)
    logger.info(f"[ORDER_WS] Запуск {len(groups)} websocket-соединений для групп тикеров")
    
    tasks = []
    for group in groups:
        tasks.append(asyncio.create_task(binance_listener_group(group)))
    return tasks


async def execute_db_operations() -> None:
    """Выполняет накопленные операции с БД.
    
    Обрабатывает pending_db_operations:
    - INSERT для новых плотностей
    - UPDATE для существующих
    - DELETE для исчезнувших
    """
    global pending_db_operations
    
    if not pending_db_operations:
        return
    
    # Копируем и очищаем буфер
    operations = pending_db_operations.copy()
    pending_db_operations.clear()
    
    # Группируем операции по типу
    inserts = []
    updates = []
    deletes = []
    
    for op in operations:
        if op["operation"] == "INSERT":
            inserts.append(op)
        elif op["operation"] == "UPDATE":
            updates.append(op)
        elif op["operation"] == "DELETE":
            deletes.append(op)
    
    current_time = dt.datetime.now(dt.timezone.utc)
    
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            # Выполняем INSERT операции
            if inserts:
                insert_rows = []
                for op in inserts:
                    data = op["data"]
                    duration_sec = (data["last_updated"] - data["first_seen"]) // 1000
                    insert_rows.append((
                        current_time,
                        data["symbol"],
                        data["order_type"],
                        data["price"],
                        data["current_size_usd"],
                        data["max_size_usd"],
                        data["touched"],
                        data["reduction_usd"],
                        data["percent_from_market"],
                        dt.datetime.fromtimestamp(data["first_seen"] / 1000, tz=dt.timezone.utc),
                        dt.datetime.fromtimestamp(data["last_updated"] / 1000, tz=dt.timezone.utc),
                        max(0, duration_sec)
                    ))
                
                await conn.executemany(_SQL_INSERT_DENSITY, insert_rows)
                logger.info(f"[ORDER_DB] Вставлено {len(inserts)} новых плотностей")
            
            # Выполняем UPDATE операции
            if updates:
                update_rows = []
                for op in updates:
                    data = op["data"]
                    duration_sec = (data["last_updated"] - data["first_seen"]) // 1000
                    update_rows.append((
                        current_time,
                        data["current_size_usd"],
                        data["max_size_usd"],
                        data["touched"],
                        data["reduction_usd"],
                        data["percent_from_market"],
                        dt.datetime.fromtimestamp(data["last_updated"] / 1000, tz=dt.timezone.utc),
                        max(0, duration_sec),
                        data["symbol"],
                        data["price"]
                    ))
                
                await conn.executemany(_SQL_UPDATE_DENSITY, update_rows)
                logger.info(f"[ORDER_DB] Обновлено {len(updates)} плотностей")
            
            # Выполняем DELETE операции
            if deletes:
                delete_rows = [(op["key"][0], op["key"][1]) for op in deletes]
                await conn.executemany(_SQL_DELETE_DENSITY, delete_rows)
                logger.info(f"[ORDER_DB] Удалено {len(deletes)} плотностей")
                
    except Exception as e:
        logger.error(f"[ORDER_DB] Ошибка при выполнении операций БД: {e}")


async def update_tickers_task() -> None:
    """Периодически обновляет список тикеров каждый час.

    Вызывает fetch_futures_tickers, очищает и заполняет SYMBOLS.
    """
    while True:
        try:
            await asyncio.sleep(3600)
            tickers = await fetch_futures_tickers()
            SYMBOLS.clear()
            SYMBOLS.extend(tickers)
            logger.info(f"[ORDER_TICKERS] Обновлён список тикеров Binance Futures: {len(SYMBOLS)} символов")
        except Exception as e:
            logger.error(f"[ORDER_TICKERS] Ошибка при обновлении тикеров: {e}")
            await asyncio.sleep(60)


async def save_densities_task() -> None:
    """Периодически сохраняет данные о плотности ордеров в базу данных.

    Вызывает execute_db_operations каждые ORDER_TRACKER_BATCH_INTERVAL секунд.
    """
    while True:
        try:
            await asyncio.sleep(ORDER_TRACKER_BATCH_INTERVAL)
            await execute_db_operations()
        except Exception as e:
            logger.error(f"[ORDER_DB] Ошибка при сохранении плотностей: {e}")
            await asyncio.sleep(ORDER_TRACKER_BATCH_INTERVAL)


async def cleanup_old_densities() -> None:
    """Очищает устаревшие записи из памяти.

    Удаляет записи order_densities старше 1 часа для предотвращения
    неконтролируемого роста памяти.
    """
    current_time = int(time.time() * 1000)
    max_age_ms = 3600 * 1000  # 1 час
    
    keys_to_remove = []
    for key, density in order_densities.items():
        if current_time - density["last_updated"] > max_age_ms:
            keys_to_remove.append(key)
    
    for key in keys_to_remove:
        # Создаём операцию удаления для БД
        pending_db_operations.append(DensityDBOperation(
            operation="DELETE",
            data=None,
            key=key
        ))
        del order_densities[key]
    
    if keys_to_remove:
        logger.info(f"[ORDER_CLEANUP] Удалено {len(keys_to_remove)} устаревших записей из памяти")


async def cleanup_out_of_range_densities() -> None:
    """Удаляет записи плотности, выходящие за диапазон ±10% от текущей рыночной цены.
    
    Проверяет каждую запись в order_densities и удаляет те, которые находятся
    за пределами допустимого отклонения MAX_PRICE_DEVIATION_PERCENT от текущей
    рыночной цены.
    """
    current_time = int(time.time() * 1000)
    keys_to_remove = []
    
    for key, density in order_densities.items():
        symbol, price = key
        
        # Получаем текущую рыночную цену из кэша
        ticker_data = TICKER_CACHE.get(symbol)
        if not ticker_data:
            continue
            
        # Проверяем актуальность данных в кэше (не старше 5 минут)
        if current_time - ticker_data["timestamp"] > 300000:  # 5 минут
            continue
            
        reference_price = ticker_data["mid"]
        if reference_price == 0:
            continue
            
        # Проверяем, находится ли цена в допустимом диапазоне
        if not is_within_tracking_range(price, reference_price):
            keys_to_remove.append(key)
            logger.debug(
                f"[ORDER_CLEANUP] Запись {symbol}@{price} выходит за диапазон ±{MAX_PRICE_DEVIATION_PERCENT}%: "
                f"текущая цена {reference_price}, отклонение {abs(calculate_price_percentage(price, reference_price)):.2f}%"
            )
    
    # Удаляем записи, выходящие за диапазон
    for key in keys_to_remove:
        pending_db_operations.append(DensityDBOperation(
            operation="DELETE",
            data=None,
            key=key
        ))
        del order_densities[key]
    
    if keys_to_remove:
        logger.info(f"[ORDER_CLEANUP] Удалено {len(keys_to_remove)} записей, выходящих за диапазон ±{MAX_PRICE_DEVIATION_PERCENT}%")


async def cleanup_price_range_task() -> None:
    """Периодически очищает записи, выходящие за диапазон ±10% каждые 5 минут.
    
    Поскольку цены двигаются быстро, проверка отклонений должна происходить 
    чаще, чем очистка по времени.
    """
    while True:
        try:
            await asyncio.sleep(300)  # 5 минут
            await cleanup_out_of_range_densities()
        except Exception as e:
            logger.error(f"[ORDER_CLEANUP_RANGE] Ошибка при очистке записей по отклонению цены: {e}")
            await asyncio.sleep(60)


async def cleanup_task() -> None:
    """Периодически очищает старые данные каждые 30 минут.
    
    Удаляет записи order_densities старше 1 часа.
    """
    while True:
        try:
            await asyncio.sleep(1800)  # 30 минут
            await cleanup_old_densities()
        except Exception as e:
            logger.error(f"[ORDER_CLEANUP] Ошибка при очистке данных: {e}")
            await asyncio.sleep(60)