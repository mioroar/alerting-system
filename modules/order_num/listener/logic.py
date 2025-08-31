import asyncpg
from typing import Tuple

from modules.listener import Listener


class OrderNumListener(Listener):
    """Отслеживает процентное изменение количества сделок.
    
    Сравнивает количество агрегированных сделок за текущее окно
    с количеством за предыдущее окно того же размера.
    
    Attributes:
        condition_id (str): Уникальный идентификатор условия.
        direction (str): Направление сравнения ('>' или '<').
        percent (float): Процент изменения для срабатывания.
        interval (int): Интервал проверки в секундах.
        window_sec (int): Размер окна для подсчета в секундах.
        matched (list[Tuple[str, float, int, int]]): (символ, % изменения, текущее, предыдущее).
    """

    def __init__(
        self,
        condition_id: str,
        direction: str,
        percent: float,
        interval: int,
        window_sec: int | None = None,
    ) -> None:
        """Инициализирует слушатель количества сделок.

        Args:
            condition_id: Уникальный идентификатор условия.
            direction: Направление сравнения ('>' или '<').
            percent: Процентное изменение для срабатывания.
            interval: Интервал проверки в секундах.
            window_sec: Размер окна для анализа в секундах.
        """
        super().__init__(condition_id, direction, percent, interval, window_sec)
        self.matched: list[Tuple[str, float, int, int]] = []

    @property
    def period_sec(self) -> int:
        """Возвращает интервал между обновлениями.
        
        Returns:
            int: Интервал в секундах.
        """
        return self.interval

    async def update_state(self, db_pool: asyncpg.Pool) -> None:
        """Обновляет состояние слушателя данными из БД.

        Вычисляет процентное изменение количества сделок между
        текущим окном и предыдущим окном того же размера.

        Args:
            db_pool: Пул соединений с базой данных.
            
        Raises:
            asyncpg.PostgresError: При ошибке выполнения SQL-запроса.
        """
        self.matched.clear()
        
        async with db_pool.acquire() as conn:
            # Получаем суммы сделок для текущего и предыдущего окна
            rows = await conn.fetch(
                """
                WITH windows AS (
                    SELECT 
                        symbol,
                        SUM(CASE 
                            WHEN ts >= NOW() - $1 * INTERVAL '1 second' 
                            THEN trade_count 
                            ELSE 0 
                        END) AS current_count,
                        SUM(CASE 
                            WHEN ts >= NOW() - 2 * $1 * INTERVAL '1 second' 
                                AND ts < NOW() - $1 * INTERVAL '1 second'
                            THEN trade_count 
                            ELSE 0 
                        END) AS previous_count
                    FROM trade_count
                    WHERE ts >= NOW() - 2 * $1 * INTERVAL '1 second'
                    GROUP BY symbol
                    HAVING SUM(CASE 
                        WHEN ts >= NOW() - 2 * $1 * INTERVAL '1 second' 
                            AND ts < NOW() - $1 * INTERVAL '1 second'
                        THEN trade_count 
                        ELSE 0 
                    END) > 0  -- Исключаем символы без предыдущих данных
                )
                SELECT 
                    symbol,
                    current_count::integer,
                    previous_count::integer,
                    CASE 
                        WHEN previous_count > 0 
                        THEN ((current_count::float / previous_count) - 1) * 100
                        ELSE NULL
                    END AS change_percent
                FROM windows
                WHERE previous_count > 0;  -- Исключаем деление на ноль
                """,
                self.window_sec
            )
        
        for row in rows:
            if row["change_percent"] is None:
                continue
                
            change_pct = float(row["change_percent"])
            if self._trigger(change_pct):
                self.matched.append((
                    row["symbol"],
                    change_pct,
                    row["current_count"],
                    row["previous_count"]
                ))

    async def notify(self) -> None:
        """Метод notify не используется для композитных алертов.
        
        Оставлен для совместимости с базовым классом.
        """
        pass

    def _trigger(self, change_pct: float) -> bool:
        """Проверяет условие срабатывания.

        Args:
            change_pct: Процентное изменение количества сделок.

        Returns:
            bool: True если условие выполнено.
        """
        if self.direction == ">":
            return change_pct > self.percent
        elif self.direction == "<":
            return change_pct < self.percent
        return False

    def matched_symbol_only(self) -> set[str]:
        """Возвращает множество символов со срабатыванием.
        
        Returns:
            set[str]: Множество символов.
        """
        return {item[0] for item in self.matched}