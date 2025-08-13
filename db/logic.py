import datetime as dt
from typing import Sequence

import asyncpg

from db.config import DATABASE_SETTINGS, POOL_SETTINGS
from modules.price.config import PriceInfo
from modules.volume_change.config import VolumeInfo
from modules.oi.config import OIInfo

_POOL: asyncpg.Pool | None = None

_SQL_PRICE = """
INSERT INTO price (ts, symbol, price)
VALUES ($1, $2, $3)
ON CONFLICT (ts, symbol) DO UPDATE
    SET price = EXCLUDED.price;
"""

_SQL_VOLUME = """
INSERT INTO volume (ts, symbol, volume)
VALUES ($1, $2, $3)
ON CONFLICT (ts, symbol) DO UPDATE
    SET volume = EXCLUDED.volume;
"""

_SQL_OI = """
INSERT INTO open_interest (ts, symbol, open_interest)
VALUES ($1, $2, $3)
ON CONFLICT (ts, symbol) DO UPDATE
    SET open_interest = EXCLUDED.open_interest;
"""

_SQL_FUNDING = """
INSERT INTO funding_rate (ts, symbol, funding_rate, next_funding_ts)
VALUES ($1, $2, $3, $4)
ON CONFLICT (ts, symbol) DO UPDATE
    SET funding_rate    = EXCLUDED.funding_rate,
        next_funding_ts = EXCLUDED.next_funding_ts;
"""

async def _executemany(sql: str, rows: Sequence[tuple]) -> None:
    """Общий помощник: batch‑вставка с reuse соединения."""
    if not rows:
        return
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.executemany(sql, rows)

async def get_pool() -> asyncpg.Pool:
    """Получить пул соединений с TimescaleDB.

    Ленивая инициализация: пул открывается только при первом вызове и
    переиспользуется всеми последующими корутинами.

    Returns:
        asyncpg.Pool: Асинхронный пул соединений с TimescaleDB.
    """
    global _POOL
    if _POOL is None:
        _POOL = await asyncpg.create_pool(**DATABASE_SETTINGS, **POOL_SETTINGS)
    return _POOL


async def close_pool() -> None:
    """Корректно закрывает пул соединений с базой данных.
    
    Должна вызываться при завершении работы приложения для предотвращения
    ошибок "pool is closed" в фоновых задачах.
    """
    global _POOL
    if _POOL is not None:
        await _POOL.close()
        _POOL = None


async def upsert_prices(prices: Sequence[PriceInfo]) -> None:
    """Вставляет/обновляет ценовые тикеты пачкой ``executemany``.

    Args:
        prices: Список словарей с ключами ``symbol``, ``price``, ``time``.
    """
    if not prices:
        return

    rows = [
        (
            dt.datetime.fromtimestamp(p["time"] / 1000, tz=dt.timezone.utc),
            p["symbol"],
            p["price"],
        )
        for p in prices
    ]
    await _executemany(_SQL_PRICE, rows)

async def upsert_volumes(volumes: Sequence[VolumeInfo]) -> None:
    """Batch‑вставка/апдейт объёмов.

    Args:
        volumes: Список словарей ``{"symbol": str, "volume": str, "time": int}``.
    """
    if not volumes:
        return

    rows = [
        (
            dt.datetime.fromtimestamp(v["time"] / 1000, tz=dt.timezone.utc),
            v["symbol"],
            v["volume"],
        )
        for v in volumes
    ]
    await _executemany(_SQL_VOLUME, rows)

async def upsert_open_interest(oi_data: Sequence[OIInfo]) -> None:
    """Batch upsert открытого интереса.

    Args:
        oi_data: Список словарей ``{"symbol": str, "oi": str, "time": int}``.
    """
    rows = [
        (
            dt.datetime.fromtimestamp(o["time"] / 1000, tz=dt.timezone.utc),
            o["symbol"],
            o["oi"],
        )
        for o in oi_data
    ]
    await _executemany(_SQL_OI, rows)

async def upsert_funding_rates(rows: Sequence[tuple]) -> None:
    """
    Batch‑upsert funding‑ставок.

    Args:
        rows: Список кортежей
              (ts: datetime, symbol: str, rate: str, next_ts: datetime).
    """
    if not rows:
        return
    await _executemany(_SQL_FUNDING, rows)

def _unix_ms_to_iso(ms: int) -> str:
    """Преобразует UNIX‑мс в ISO‑8601 строку ``YYYY‑MM‑DDTHH:MM:SS.mmmZ``.

    Args:
        ms (int): Миллисекунды с эпохи Unix.

    Returns:
        str: Временная метка в UTC.
    """
    return dt.datetime.utcfromtimestamp(ms / 1000).isoformat() + "Z"
