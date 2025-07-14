import datetime as dt
from typing import Sequence

import asyncpg

from db.config import DATABASE_SETTINGS, POOL_SETTINGS
from modules.price.config import PriceInfo

_POOL: asyncpg.Pool | None = None
_SQL = """
INSERT INTO price (ts, symbol, price)
VALUES ($1, $2, $3)
ON CONFLICT (ts, symbol) DO UPDATE
    SET price = EXCLUDED.price;
"""


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

    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.executemany(_SQL, rows)

def _unix_ms_to_iso(ms: int) -> str:
    """Преобразует UNIX‑мс в ISO‑8601 строку ``YYYY‑MM‑DDTHH:MM:SS.mmmZ``.

    Args:
        ms (int): Миллисекунды с эпохи Unix.

    Returns:
        str: Временная метка в UTC.
    """
    return dt.datetime.utcfromtimestamp(ms / 1000).isoformat() + "Z"
