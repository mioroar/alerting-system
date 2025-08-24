import httpx
import asyncio
import time
from typing import List, Set
from collections import deque
from datetime import datetime, timedelta

from modules.oi.config import EXINFO_API_URL, OI_API_URL, OIInfo, _get_client
from modules.config import TICKER_BLACKLIST
from config import logger

_FAILED_SYMBOLS: Set[str] = set()
_FAILED_SYMBOLS_TTL: dict[str, float] = {}
_CACHE_DURATION = 3600

_REQUEST_TIMES: deque = deque(maxlen=1200)
_RATE_LIMIT_WINDOW = 60
_MAX_REQUESTS_PER_WINDOW = 1000
_CONCURRENT_REQUESTS = 10

_semaphore = asyncio.Semaphore(_CONCURRENT_REQUESTS)

async def _check_rate_limit() -> None:
    """Проверяет и ожидает, если достигнут лимит запросов.
    
    Binance имеет лимит 1200 запросов в минуту для /fapi/v1/openInterest.
    Мы используем скользящее окно для отслеживания запросов.
    """
    current_time = time.time()
    
    while _REQUEST_TIMES and _REQUEST_TIMES[0] < current_time - _RATE_LIMIT_WINDOW:
        _REQUEST_TIMES.popleft()
    
    if len(_REQUEST_TIMES) >= _MAX_REQUESTS_PER_WINDOW:
        wait_time = _RATE_LIMIT_WINDOW - (current_time - _REQUEST_TIMES[0]) + 1
        if wait_time > 0:
            logger.warning("Rate limit reached, waiting %.1f seconds", wait_time)
            await asyncio.sleep(wait_time)
            await _check_rate_limit()
    
    _REQUEST_TIMES.append(current_time)

def _is_symbol_blacklisted(symbol: str) -> bool:
    """Проверяет, находится ли символ в черном списке.

    Args:
        symbol: Символ торговой пары для проверки.

    Returns:
        bool: True если символ в черном списке, False иначе.

    Raises:
        None
    """
    current_time = time.time()
    
    expired_symbols = [
        sym for sym, expire_time in _FAILED_SYMBOLS_TTL.items()
        if current_time > expire_time
    ]
    for sym in expired_symbols:
        _FAILED_SYMBOLS.discard(sym)
        _FAILED_SYMBOLS_TTL.pop(sym, None)
    
    return symbol in _FAILED_SYMBOLS

def _add_to_blacklist(symbol: str) -> None:
    """Добавляет символ в черный список на определенное время.

    Args:
        symbol: Символ торговой пары для добавления в черный список.

    Returns:
        None

    Raises:
        None

    Note:
        Символ остается в черном списке на время _CACHE_DURATION секунд.
    """
    _FAILED_SYMBOLS.add(symbol)
    _FAILED_SYMBOLS_TTL[symbol] = time.time() + _CACHE_DURATION
    logger.debug("Added %s to temporary blacklist", symbol)

async def _get_perp_symbols() -> list[str]:
    """Возвращает список символов perpetual-фьючерсов Binance.

    Исключает пары из ``TICKER_BLACKLIST`` и временно проблемные символы.

    Returns:
        list[str]: Список символов perpetual-фьючерсов, доступных для торговли.

    Raises:
        Exception: При ошибке получения данных с Binance API.

    Note:
        Исключает символы, которые находятся в черном списке или не торгуются.
    """
    try:
        client = await _get_client()
        
        await _check_rate_limit()
        
        resp = await client.get(EXINFO_API_URL, timeout=15)
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
        
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 429:
            logger.error("Rate limit exceeded on exchange info endpoint")
            await asyncio.sleep(60)
        else:
            logger.exception("HTTP error fetching exchange info: %s", exc)
        return []
    except Exception as exc:
        logger.exception("Error fetching exchange info: %s", exc)
        return []

async def _fetch_single(symbol: str) -> OIInfo | None:
    """Получить OI для одного символа с rate limiting.

    Args:
        symbol: Символ торговой пары для получения данных OI.

    Returns:
        OIInfo | None: Информация об открытом интересе для символа или None в случае ошибки.
    """
    if _is_symbol_blacklisted(symbol):
        return None
    
    async with _semaphore:
        await _check_rate_limit()
        
        client = await _get_client()
        params = {"symbol": symbol}
        
        try:
            resp = await client.get(OI_API_URL, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            
            if "openInterest" not in data:
                logger.warning("Missing openInterest field for %s", symbol)
                return None
            
            return {
                "symbol": symbol,
                "oi": str(data["openInterest"]),
                "time": int(data.get("time") or data.get("timestamp") or time.time() * 1000),
            }
            
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429:
                logger.error("Rate limit exceeded for %s, backing off", symbol)
                await asyncio.sleep(60)
                return None
            elif exc.response.status_code in (400, 404):
                _add_to_blacklist(symbol)
                logger.warning("Symbol %s not available (HTTP %d), blacklisted temporarily", 
                             symbol, exc.response.status_code)
            else:
                logger.warning("OI API HTTP error %s (%d): %s", 
                             symbol, exc.response.status_code, exc.response.text[:200])
            return None
            
        except httpx.TimeoutException:
            logger.warning("OI API timeout for %s", symbol)
            await asyncio.sleep(0.5)
            return None
            
        except httpx.RequestError as exc:
            logger.warning("OI API request error %s: %s", symbol, exc)
            return None
            
        except (KeyError, ValueError, TypeError) as exc:
            logger.warning("OI API data error %s: %s", symbol, exc)
            return None
            
        except Exception as exc:
            logger.warning("OI API unexpected error %s: %s", symbol, exc)
            return None

async def fetch_oi_info() -> List[OIInfo]:
    """Собираем OI с учетом rate limiting.

    Получает информацию об открытом интересе для всех доступных perpetual-фьючерсов
    с ограничением одновременных запросов и соблюдением rate limits.

    Returns:
        List[OIInfo]: Список информации об открытом интересе для всех успешно обработанных символов.
    """
    symbols = await _get_perp_symbols()
    
    if not symbols:
        logger.warning("No symbols available for OI collection")
        return []
    
    logger.debug("Fetching OI for %d symbols with rate limiting", len(symbols))
    
    batch_size = 50
    successful_results = []
    
    for i in range(0, len(symbols), batch_size):
        batch = symbols[i:i+batch_size]
        logger.debug("Processing batch %d/%d", i//batch_size + 1, (len(symbols) + batch_size - 1)//batch_size)
        
        tasks = [_fetch_single(sym) for sym in batch]
        
        try:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            error_count = 0
            
            for j, result in enumerate(results):
                if isinstance(result, Exception):
                    error_count += 1
                    logger.debug("Task failed for symbol %s: %s", batch[j], result)
                elif result is not None:
                    successful_results.append(result)
            
            if error_count > 0:
                logger.debug("Batch completed: %d successful, %d failed", 
                           len([r for r in results if r and not isinstance(r, Exception)]), 
                           error_count)
            
            if i + batch_size < len(symbols):
                await asyncio.sleep(1)
                
        except Exception as exc:
            logger.exception("Error processing batch: %s", exc)
            continue
    
    logger.info("OI collection completed: %d successful out of %d symbols, %d blacklisted", 
               len(successful_results), len(symbols), len(_FAILED_SYMBOLS))
    
    return successful_results

def get_blacklist_stats() -> dict:
    """Возвращает статистику черного списка для мониторинга.

    Returns:
        dict: Словарь со статистикой черного списка.
    """
    current_time = time.time()
    active_blacklist = [
        sym for sym, expire_time in _FAILED_SYMBOLS_TTL.items()
        if current_time <= expire_time
    ]
    
    rate_limit_info = {
        "current_requests_in_window": len(_REQUEST_TIMES),
        "max_requests_per_window": _MAX_REQUESTS_PER_WINDOW,
        "window_seconds": _RATE_LIMIT_WINDOW,
        "concurrent_limit": _CONCURRENT_REQUESTS
    }
    
    return {
        "blacklisted_count": len(active_blacklist),
        "blacklisted_symbols": active_blacklist,
        "cache_duration_sec": _CACHE_DURATION,
        "rate_limit_info": rate_limit_info
    }

def reset_rate_limiter():
    """Сбрасывает счетчик rate limiter."""
    global _REQUEST_TIMES
    _REQUEST_TIMES.clear()
    logger.info("Rate limiter reset")