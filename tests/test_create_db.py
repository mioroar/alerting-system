import asyncio, asyncpg
from time import timezone
import datetime as dt

DSN = "postgresql://postgres:Serfcxd123@localhost:5433/price_screener"

async def healthcheck() -> None:
    conn = await asyncpg.connect(DSN)
    try:
        exists = await conn.fetchval("""
            SELECT to_regclass('public.price') IS NOT NULL
        """)
        print("price table exists 👉", exists)
        rows = await conn.fetch("SELECT COUNT(*) AS cnt FROM price")
        print("rows in price     👉", rows[0]["cnt"])
    finally:
        await conn.close()

async def smoke_test() -> None:
    """Вставляет тестовую цену и проверяет, что она видна."""
    async with asyncpg.create_pool(dsn=DSN, min_size=1, max_size=2) as pool:
        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO price (ts, symbol, price) VALUES ($1, $2, $3)",
                dt.datetime.now(dt.timezone.utc), "TEST", 123.456,
            )
            # чтение
            row = await conn.fetchrow(
                "SELECT ts, symbol, price FROM price ORDER BY ts DESC LIMIT 1"
            )
            print("last row 👉", dict(row))

async def delete_test() -> None:
    async with asyncpg.create_pool(dsn=DSN, min_size=1, max_size=2) as pool:
        async with pool.acquire() as conn:
            rows = await conn.execute(
                "DELETE FROM price WHERE symbol = $1",
                "TEST",
            )
            print("удалено строк:", rows.split()[-1])  # 'DELETE 1'

asyncio.run(healthcheck())
asyncio.run(smoke_test())
asyncio.run(delete_test())