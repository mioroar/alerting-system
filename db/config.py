import os
from typing import Any

DATABASE_SETTINGS: dict[str, Any] = {
    "database": os.getenv("DB_NAME", "price_screener"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", "1234"),
    "host": os.getenv("DB_HOST", "127.0.0.1"),
    "port": int(os.getenv("DB_PORT", 5433)),
}

POOL_SETTINGS: dict[str, int | float] = {
    "min_size": 20,
    "max_size": 80,
    "max_inactive_connection_lifetime": 300.0,
    "command_timeout": 30,
}