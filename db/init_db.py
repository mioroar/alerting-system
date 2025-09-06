import asyncpg
from typing import Final, Dict, List, Tuple
from dataclasses import dataclass
from config import logger
from db.config import DATABASE_SETTINGS


@dataclass
class TableConfig:
    """Конфигурация таблицы с SQL запросами для создания и индексов.
    
    Attributes:
        name: Название таблицы
        create_sql: SQL запрос для создания таблицы
        is_hypertable: Нужно ли создавать hypertable
        indexes: Список SQL запросов для создания индексов
        retention_hours: Количество часов для политики хранения данных
    """
    name: str
    create_sql: str
    is_hypertable: bool = False
    indexes: List[str] = None
    retention_hours: int = 24
    
    def __post_init__(self) -> None:
        """Инициализирует пустой список индексов если не передан."""
        if self.indexes is None:
            self.indexes = []


async def _execute_with_logging(
    conn: asyncpg.Connection, 
    sql: str, 
    operation_description: str
) -> None:
    """Выполняет SQL запрос с логированием операции.
    
    Args:
        conn: Соединение с базой данных
        sql: SQL запрос для выполнения
        operation_description: Описание операции для логирования
    """
    try:
        logger.info(f"Executing: {operation_description}")
        await conn.execute(sql)
        logger.info(f"Successfully completed: {operation_description}")
    except Exception as e:
        logger.error(f"Failed to execute {operation_description}: {e}")
        raise


def _get_table_configs() -> List[TableConfig]:
    """Возвращает конфигурации всех таблиц базы данных.
    
    Returns:
        List[TableConfig]: Список конфигураций таблиц
    """
    return [
        TableConfig(
            name="price",
            create_sql="""
                CREATE TABLE IF NOT EXISTS price (
                    ts     TIMESTAMPTZ   NOT NULL,
                    symbol TEXT          NOT NULL,
                    price  NUMERIC(18,8) NOT NULL,
                    CONSTRAINT price_pk PRIMARY KEY (ts, symbol)
                );
            """,
            is_hypertable=True,
            indexes=[
                """CREATE INDEX IF NOT EXISTS price_symbol_ts_desc_idx
                   ON price (symbol, ts DESC) INCLUDE (price);"""
            ],
            retention_hours=24
        ),
        
        TableConfig(
            name="trade_count",
            create_sql="""
                CREATE TABLE IF NOT EXISTS trade_count (
                    ts          TIMESTAMPTZ   NOT NULL,
                    symbol      TEXT          NOT NULL,
                    trade_count INTEGER       NOT NULL,
                    CONSTRAINT trade_count_pk PRIMARY KEY (ts, symbol)
                );
            """,
            is_hypertable=True,
            indexes=[
                """CREATE INDEX IF NOT EXISTS trade_count_symbol_ts_desc_idx
                   ON trade_count (symbol, ts DESC) INCLUDE (trade_count);"""
            ],
            retention_hours=24
        ),
        
        TableConfig(
            name="volume",
            create_sql="""
                CREATE TABLE IF NOT EXISTS volume (
                    ts     TIMESTAMPTZ   NOT NULL,
                    symbol TEXT          NOT NULL,
                    volume NUMERIC(18,8) NOT NULL,
                    CONSTRAINT volume_pk PRIMARY KEY (ts, symbol)
                );
            """,
            is_hypertable=True,
            retention_hours=24
        ),
        
        TableConfig(
            name="open_interest",
            create_sql="""
                CREATE TABLE IF NOT EXISTS open_interest (
                    ts            TIMESTAMPTZ    NOT NULL,
                    symbol        TEXT           NOT NULL,
                    open_interest NUMERIC(24, 8) NOT NULL,
                    CONSTRAINT open_interest_pk PRIMARY KEY (ts, symbol)
                );
            """,
            is_hypertable=True,
            retention_hours=24
        ),
        
        TableConfig(
            name="funding_rate",
            create_sql="""
                CREATE TABLE IF NOT EXISTS funding_rate (
                    ts               TIMESTAMPTZ   NOT NULL,
                    symbol           TEXT          NOT NULL,
                    funding_rate     NUMERIC(16,8) NOT NULL,
                    next_funding_ts  TIMESTAMPTZ   NOT NULL,
                    CONSTRAINT funding_rate_pk PRIMARY KEY (ts, symbol)
                );
            """,
            is_hypertable=True,
            retention_hours=48
        ),
        
        TableConfig(
            name="order_density",
            create_sql="""
                CREATE TABLE IF NOT EXISTS order_density (
                    ts TIMESTAMPTZ NOT NULL,
                    symbol VARCHAR(20) NOT NULL,
                    order_type VARCHAR(10) NOT NULL,
                    price DECIMAL(20, 8) NOT NULL,
                    current_size_usd DECIMAL(20, 2) NOT NULL,
                    max_size_usd DECIMAL(20, 2) NOT NULL,
                    touched BOOLEAN DEFAULT FALSE,
                    reduction_usd DECIMAL(20, 2) DEFAULT 0,
                    percent_from_market DECIMAL(10, 4) NOT NULL,
                    first_seen TIMESTAMPTZ NOT NULL,
                    last_updated TIMESTAMPTZ NOT NULL,
                    duration_sec INTEGER DEFAULT 0,
                    
                    -- Уникальный ключ по символу и цене
                    PRIMARY KEY (symbol, price)
                );
            """,
            is_hypertable=False,
            indexes=[
                "CREATE INDEX IF NOT EXISTS idx_order_density_ts ON order_density(ts DESC);",
                "CREATE INDEX IF NOT EXISTS idx_order_density_symbol ON order_density(symbol);",
                "CREATE INDEX IF NOT EXISTS idx_order_density_touched ON order_density(touched) WHERE touched = true;",
                "CREATE INDEX IF NOT EXISTS idx_order_density_size ON order_density(current_size_usd DESC);",
                "CREATE INDEX IF NOT EXISTS idx_order_density_reduction ON order_density(reduction_usd DESC) WHERE reduction_usd > 0;",
            ],
            retention_hours=48
        )
    ]


async def _create_timescale_extension(conn: asyncpg.Connection) -> None:
    """Создает расширение TimescaleDB.
    
    Args:
        conn: Соединение с базой данных
    """
    await _execute_with_logging(
        conn, 
        "CREATE EXTENSION IF NOT EXISTS timescaledb;",
        "Create TimescaleDB extension"
    )


async def _create_table(conn: asyncpg.Connection, config: TableConfig) -> None:
    """Создает таблицу согласно конфигурации.
    
    Args:
        conn: Соединение с базой данных
        config: Конфигурация таблицы
    """
    await _execute_with_logging(
        conn,
        config.create_sql,
        f"Create {config.name} table"
    )


async def _create_hypertable(conn: asyncpg.Connection, table_name: str) -> None:
    """Создает hypertable для указанной таблицы.
    
    Args:
        conn: Соединение с базой данных
        table_name: Название таблицы
    """
    sql = f"SELECT create_hypertable('{table_name}', by_range('ts'), if_not_exists => TRUE);"
    await _execute_with_logging(
        conn,
        sql,
        f"Create {table_name} hypertable"
    )


async def _create_indexes(conn: asyncpg.Connection, config: TableConfig) -> None:
    """Создает индексы для таблицы.
    
    Args:
        conn: Соединение с базой данных
        config: Конфигурация таблицы с индексами
    """
    for index_sql in config.indexes:
        await _execute_with_logging(
            conn,
            index_sql,
            f"Create index for {config.name}"
        )


async def _add_retention_policy(
    conn: asyncpg.Connection, 
    table_name: str, 
    hours: int
) -> None:
    """Добавляет политику хранения данных для таблицы.
    
    Args:
        conn: Соединение с базой данных
        table_name: Название таблицы
        hours: Количество часов для хранения данных
    """
    sql = f"SELECT add_retention_policy('{table_name}', INTERVAL '{hours} hours', if_not_exists => TRUE);"
    await _execute_with_logging(
        conn,
        sql,
        f"Add {table_name} retention policy ({hours}h)"
    )


async def init_db() -> None:
    """Создает таблицы, hypertables и политики хранения данных.
    
    Выполняет полную инициализацию базы данных по шагам:
    1. Создание расширения TimescaleDB
    2. Создание таблиц
    3. Создание hypertables
    4. Создание индексов
    5. Настройка политик хранения данных
    """
    conn: asyncpg.Connection = await asyncpg.connect(**DATABASE_SETTINGS)
    
    try:
        # Создание расширения TimescaleDB
        await _create_timescale_extension(conn)
        
        # Получение конфигураций таблиц
        table_configs = _get_table_configs()
        
        # Создание всех таблиц
        for config in table_configs:
            await _create_table(conn, config)
        
        # Создание hypertables
        for config in table_configs:
            if config.is_hypertable:
                await _create_hypertable(conn, config.name)
        
        # Создание индексов
        for config in table_configs:
            if config.indexes:
                await _create_indexes(conn, config)
        
        # Добавление политик хранения данных
        for config in table_configs:
            if config.is_hypertable:
                await _add_retention_policy(conn, config.name, config.retention_hours)
        
        logger.info("Database initialization completed successfully")
        
    finally:
        await conn.close()