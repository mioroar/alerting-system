import asyncpg

from typing import Final

from db.config import DATABASE_SETTINGS

_INIT_SQL: Final[str] = """
CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE IF NOT EXISTS price (
    ts     TIMESTAMPTZ   NOT NULL,
    symbol TEXT          NOT NULL,
    price  NUMERIC(18,8) NOT NULL,
    CONSTRAINT price_pk PRIMARY KEY (ts, symbol)
);

SELECT create_hypertable('price', by_range('ts'), if_not_exists => TRUE);
SELECT add_retention_policy('price', INTERVAL '24 hours', if_not_exists => TRUE);
"""


async def init_db() -> None:
    """Создаёт таблицу, hypertable и политики, если их ещё нет."""
    conn: asyncpg.Connection = await asyncpg.connect(**DATABASE_SETTINGS)
    try:
        await conn.execute(_INIT_SQL)
    finally:
        await conn.close()