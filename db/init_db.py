import asyncpg
from typing import Final
from config import logger
from db.config import DATABASE_SETTINGS


async def init_db() -> None:
    """Создаёт таблицы, hypertables и политики, если их ещё нет.
    
    Выполняет инициализацию базы данных по шагам с обработкой ошибок
    для предотвращения проблем с дублированием объектов.
    """
    conn: asyncpg.Connection = await asyncpg.connect(**DATABASE_SETTINGS)
    try:
        # Создание расширения TimescaleDB
        try:
            await conn.execute("CREATE EXTENSION IF NOT EXISTS timescaledb;")
            logger.info("TimescaleDB extension enabled successfully")
        except Exception as e:
            logger.warning(f"Failed to create TimescaleDB extension: {e}")

        # Создание таблицы price
        try:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS price (
                    ts     TIMESTAMPTZ   NOT NULL,
                    symbol TEXT          NOT NULL,
                    price  NUMERIC(18,8) NOT NULL,
                    CONSTRAINT price_pk PRIMARY KEY (ts, symbol)
                );
            """)
            logger.info("Price table created successfully")
        except Exception as e:
            logger.warning(f"Failed to create price table: {e}")

        # Создание таблицы volume
        try:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS volume (
                    ts     TIMESTAMPTZ   NOT NULL,
                    symbol TEXT          NOT NULL,
                    volume NUMERIC(18,8) NOT NULL,
                    CONSTRAINT volume_pk PRIMARY KEY (ts, symbol)
                );
            """)
            logger.info("Volume table created successfully")
        except Exception as e:
            logger.warning(f"Failed to create volume table: {e}")

        try:
            await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS open_interest (
            ts            TIMESTAMPTZ    NOT NULL,
            symbol        TEXT           NOT NULL,
            open_interest NUMERIC(24, 8) NOT NULL,
            CONSTRAINT open_interest_pk PRIMARY KEY (ts, symbol)
        );
        """
        )
        except Exception as e:
            logger.warning(f"Failed to create open_interest table: {e}")

        # Создание hypertable для price
        try:
            await conn.execute(
                "SELECT create_hypertable('price', by_range('ts'), if_not_exists => TRUE);"
            )
            logger.info("Price hypertable created successfully")
        except Exception as e:
            logger.warning(f"Failed to create price hypertable: {e}")

        # Создание hypertable для volume
        try:
            await conn.execute(
                "SELECT create_hypertable('volume', by_range('ts'), if_not_exists => TRUE);"
            )
            logger.info("Volume hypertable created successfully")
        except Exception as e:
            logger.warning(f"Failed to create volume hypertable: {e}")

        try:
            await conn.execute(
                "SELECT create_hypertable('open_interest', by_range('ts'), if_not_exists => TRUE);"
            )
            logger.info("Open interest hypertable created successfully")
        except Exception as e:
            logger.warning(f"Failed to create open interest hypertable: {e}")

        # Добавление retention policy для price
        try:
            await conn.execute(
                "SELECT add_retention_policy('price', INTERVAL '24 hours', if_not_exists => TRUE);"
            )
            logger.info("Price retention policy added successfully")
        except Exception as e:
            logger.warning(f"Failed to add price retention policy: {e}")

        # Добавление retention policy для volume
        try:
            await conn.execute(
                "SELECT add_retention_policy('volume', INTERVAL '24 hours', if_not_exists => TRUE);"
            )
            logger.info("Volume retention policy added successfully")
        except Exception as e:
            logger.warning(f"Failed to add volume retention policy: {e}")

        try:
            await conn.execute(
                "SELECT add_retention_policy('open_interest', INTERVAL '24 hours', if_not_exists => TRUE);"
            )
            logger.info("Open interest retention policy added successfully")
        except Exception as e:
            logger.warning(f"Failed to add open interest retention policy: {e}")

        logger.info("Database initialization completed")

    finally:
        await conn.close()
