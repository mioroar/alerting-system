import asyncio
import httpx
import time
from typing import List, Set
from collections import deque

from config import logger
from modules.config import TICKER_BLACKLIST
from modules.order_num.config import (
    KLINES_API_URL,
    EXCHANGE_INFO_API_URL,
    TradeCountInfo,
    CONCURRENT_REQUESTS,
    RATE_LIMIT_PER_MINUTE,
    HTTP_TIMEOUT,
    MAX_RETRIES,
    MAX_KLINES_PER_REQUEST,
    KLINE_INTERVAL,
)

# Rate limiting
_REQUEST_TIMES: deque = deque(maxlen=RATE_LIMIT_PER_MINUTE)
_RATE_LIMIT_WINDOW = 60
_semaphore = asyncio.Semaphore(CONCURRENT_REQUESTS)

# HTTP client
_CLIENT: httpx.AsyncClient | None = None

# Cache для проблемных символов
_FAILED_SYMBOLS: Set[str] = set()
_FAILED_SYMBOLS_TTL: dict[str, float] = {}
_CACHE_DURATION = 3600


async def _get_client() -> httpx.AsyncClient:
    """Возвращает глобальный HTTP клиент.
    
    Returns:
        httpx.AsyncClient: Настроенный HTTP клиент.
    """
    global _CLIENT
    if _CLIENT is None or _CLIENT.is_closed:
        _CLIENT = httpx.AsyncClient(
            timeout=httpx.Timeout(HTTP_TIMEOUT),
            limits=httpx.Limits(
                max_connections=100,
                max_keepalive_connections=50
            ),
            transport=httpx.AsyncHTTPTransport(
                retries=MAX_RETRIES,
                http2=False
            ),
            headers={
                "User-Agent": "TradingBot/1.0",
                "Accept": "application/json",
                "Connection": "keep-alive"
            }
        )
    return _CLIENT


async def close_client() -> None:
    """Закрывает HTTP клиент."""
    global _CLIENT
    if _CLIENT is not None and not _CLIENT.is_closed:
        await _CLIENT.aclose()
        _CLIENT = None


async def _check_rate_limit() -> None:
    """Проверяет и ожидает, если достигнут лимит запросов."""
    current_time = time.time()
    
    # Удаляем старые записи
    while _REQUEST_TIMES and _REQUEST_TIMES[0] < current_time - _RATE_LIMIT_WINDOW:
        _REQUEST_TIMES.popleft()
    
    # Проверяем лимит
    if len(_REQUEST_TIMES) >= RATE_LIMIT_PER_MINUTE - 100:  # Оставляем запас
        wait_time = _RATE_LIMIT_WINDOW - (current_time - _REQUEST_TIMES[0]) + 1
        if wait_time > 0:
            logger.warning("Rate limit reached, waiting %.1f seconds", wait_time)
            await asyncio.sleep(wait_time)
            await _check_rate_limit()
    
    _REQUEST_TIMES.append(current_time)


def _is_symbol_blacklisted(symbol: str) -> bool:
    """Проверяет, находится ли символ в черном списке.
    
    Args:
        symbol: Символ для проверки.
        
    Returns:
        bool: True если символ в черном списке.
    """
    current_time = time.time()
    
    # Удаляем устаревшие записи
    expired_symbols = [
        sym for sym, expire_time in _FAILED_SYMBOLS_TTL.items()
        if current_time > expire_time
    ]
    for sym in expired_symbols:
        _FAILED_SYMBOLS.discard(sym)
        _FAILED_SYMBOLS_TTL.pop(sym, None)
    
    return symbol in _FAILED_SYMBOLS


def _add_to_blacklist(symbol: str) -> None:
    """Добавляет символ в черный список.
    
    Args:
        symbol: Символ для добавления.
    """
    _FAILED_SYMBOLS.add(symbol)
    _FAILED_SYMBOLS_TTL[symbol] = time.time() + _CACHE_DURATION
    logger.debug("Added %s to temporary blacklist", symbol)


async def _get_perp_symbols() -> List[str]:
    """Возвращает список активных perpetual символов.
    
    Returns:
        List[str]: Список символов.
    """
    try:
        client = await _get_client()
        await _check_rate_limit()
        
        resp = await client.get(EXCHANGE_INFO_API_URL, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        
        symbols = []
        for s in data.get("symbols", []):
            symbol = s.get("symbol", "")
            
            if (s.get("contractType") != "PERPETUAL" or 
                s.get("status") != "TRADING" or
                any(blk.lower() in symbol.lower() for blk in TICKER_BLACKLIST)):
                continue
            
            if _is_symbol_blacklisted(symbol):
                continue
            
            symbols.append(symbol)
        
        logger.debug("Found %d active perpetual symbols", len(symbols))
        return symbols
        
    except Exception as exc:
        logger.exception("Error fetching exchange info: %s", exc)
        return []


async def _fetch_klines_for_symbol(
    symbol: str, 
    limit: int = 30  # Берем последние 30 минутных свечей
) -> List[TradeCountInfo] | None:
    """Получает минутные свечи и извлекает количество сделок.
    
    Args:
        symbol: Символ торговой пары.
        limit: Количество свечей для получения.
        
    Returns:
        List[TradeCountInfo] | None: Список с количеством сделок по минутам.
    """
    if _is_symbol_blacklisted(symbol):
        return None
    
    async with _semaphore:
        await _check_rate_limit()
        
        client = await _get_client()
        params = {
            "symbol": symbol,
            "interval": KLINE_INTERVAL,
            "limit": limit
        }
        
        try:
            resp = await client.get(KLINES_API_URL, params=params, timeout=10)
            resp.raise_for_status()
            klines = resp.json()
            
            result = []
            for kline in klines:
                # kline[0] - open time (ms)
                # kline[8] - count of trades
                result.append({
                    "symbol": symbol,
                    "trade_count": int(kline[8]),
                    "time": int(kline[0])
                })
            
            return result
            
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429:
                logger.error("Rate limit exceeded for %s", symbol)
                await asyncio.sleep(60)
            elif exc.response.status_code in (400, 404):
                _add_to_blacklist(symbol)
                logger.debug("Symbol %s not available, blacklisted", symbol)
            else:
                logger.warning("HTTP error for %s: %d", symbol, exc.response.status_code)
            return None
            
        except Exception as exc:
            logger.warning("Error fetching klines for %s: %s", symbol, exc)
            return None


async def fetch_trade_counts_from_klines() -> List[TradeCountInfo]:
    """Собирает количество сделок из минутных свечей для всех символов.
    
    Returns:
        List[TradeCountInfo]: Список с информацией о количестве сделок.
    """
    symbols = await _get_perp_symbols()
    
    if not symbols:
        logger.warning("No symbols available for trade count collection")
        return []
    
    logger.info("Fetching trade counts from klines for %d symbols", len(symbols))
    
    # Обрабатываем батчами
    batch_size = 50
    all_results = []
    
    for i in range(0, len(symbols), batch_size):
        batch = symbols[i:i+batch_size]
        logger.debug("Processing batch %d/%d", 
                    i//batch_size + 1, 
                    (len(symbols) + batch_size - 1)//batch_size)
        
        tasks = [_fetch_klines_for_symbol(sym, limit=30) for sym in batch]
        
        try:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for result in results:
                if isinstance(result, Exception):
                    logger.debug("Task failed: %s", result)
                elif result is not None:
                    # Берем только последнюю полную минуту (предпоследнюю свечу)
                    # так как последняя свеча может быть неполной
                    if len(result) >= 2:
                        all_results.append(result[-2])  # Предпоследняя свеча
            
            # Пауза между батчами
            if i + batch_size < len(symbols):
                await asyncio.sleep(1)
                
        except Exception as exc:
            logger.exception("Error processing batch: %s", exc)
            continue
    
    logger.info("Trade count collection completed: %d symbols processed", 
               len(all_results))
    
    return all_results


async def fetch_historical_trade_counts(minutes_back: int = 20) -> List[TradeCountInfo]:
    """Собирает исторические данные о количестве сделок.
    
    Используется при первом запуске для заполнения БД историческими данными.
    
    Args:
        minutes_back: Количество минут истории для загрузки.
        
    Returns:
        List[TradeCountInfo]: Список с историческими данными.
    """
    symbols = await _get_perp_symbols()
    
    if not symbols:
        logger.warning("No symbols available for historical data")
        return []
    
    logger.info("Fetching historical trade counts for %d symbols, %d minutes back", 
                len(symbols), minutes_back)
    
    batch_size = 30  # Меньше батч для исторических данных
    all_results = []
    
    for i in range(0, len(symbols), batch_size):
        batch = symbols[i:i+batch_size]
        logger.debug("Processing historical batch %d/%d", 
                    i//batch_size + 1, 
                    (len(symbols) + batch_size - 1)//batch_size)
        
        tasks = [_fetch_klines_for_symbol(sym, limit=minutes_back) for sym in batch]
        
        try:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for result in results:
                if isinstance(result, Exception):
                    logger.debug("Historical task failed: %s", result)
                elif result is not None:
                    all_results.extend(result[:-1])  # Все кроме последней неполной
            
            # Пауза между батчами
            if i + batch_size < len(symbols):
                await asyncio.sleep(2)  # Больше пауза для исторических данных
                
        except Exception as exc:
            logger.exception("Error processing historical batch: %s", exc)
            continue
    
    logger.info("Historical collection completed: %d records collected", 
               len(all_results))
    
    return all_results