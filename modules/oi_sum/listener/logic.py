import asyncpg
from typing import Tuple

from modules.listener import Listener


class OISumListener(Listener):
    """Отслеживает абсолютное значение открытого интереса.
    
    Проверяет, превышает ли текущий открытый интерес заданный порог в USD.
    В отличие от OIListener, который сравнивает с медианой, этот модуль
    работает с абсолютными значениями.
    
    Attributes:
        condition_id (str): Уникальный идентификатор условия.
        direction (str): Направление сравнения ('>' или '<').
        percent (float): Пороговое значение в USD.
        interval (int): Интервал проверки в секундах.
        matched (list[Tuple[str, float]]): Список (символ, текущий OI).
    """

    def __init__(
        self,
        condition_id: str,
        direction: str,
        percent: float,
        interval: int | None = None,
        window_sec: int | None = None,
    ) -> None:
        """Инициализирует слушатель суммы OI.

        Args:
            condition_id: Уникальный идентификатор условия.
            direction: Направление сравнения ('>' или '<').
            percent: Пороговое значение открытого интереса в USD.
            interval: Интервал проверки в секундах (по умолчанию 60).
            window_sec: Длина окна расчёта в секундах (не используется).
        """
        super().__init__(condition_id, direction, percent, interval or 60, window_sec)
        self.matched: list[Tuple[str, float]] = []

    @property
    def period_sec(self) -> int:
        """Возвращает интервал между обновлениями состояния.
        
        Returns:
            int: Интервал в секундах.
        """
        return self.interval

    async def update_state(self, db_pool: asyncpg.Pool) -> None:
        """Обновляет состояние слушателя свежими данными из БД.

        Выполняет SQL-запрос для получения последнего значения OI для каждого
        символа и проверяет условия срабатывания.

        Args:
            db_pool: Пул соединений с базой данных.
            
        Raises:
            asyncpg.PostgresError: При ошибке выполнения SQL-запроса.
        """
        self.matched.clear()
        
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT DISTINCT ON (symbol)
                       symbol,
                       open_interest::numeric AS current_oi
                  FROM open_interest
                 ORDER BY symbol, ts DESC;
                """
            )
        
        for row in rows:
            current_oi: float = float(row["current_oi"])
            if self._trigger(current_oi):
                self.matched.append((row["symbol"], current_oi))

    async def notify(self) -> None:
        """Метод notify не используется для композитных алертов.
        
        Оставлен для совместимости с базовым классом, но не выполняет
        никаких действий, так как уведомления обрабатываются на уровне
        CompositeListener.
        """
        pass

    def _trigger(self, current_oi: float) -> bool:
        """Проверяет условие срабатывания на основе абсолютного значения OI.

        Args:
            current_oi: Текущее значение открытого интереса в USD.

        Returns:
            bool: True если условие сработало, False в противном случае.
        """
        if self.direction == ">":
            return current_oi > self.percent
        elif self.direction == "<":
            return current_oi < self.percent
        return False
    
    def matched_symbol_only(self) -> set[str]:
        """Возвращает множество тикеров из matched.
        
        Переопределяем метод базового класса для совместимости
        с композитными слушателями.
        
        Returns:
            set[str]: Множество символов, для которых сработало условие.
        """
        return {item[0] for item in self.matched}