import asyncpg
import datetime as dt
from modules.listener import Listener

from config import logger


class FundingListener(Listener):
    """Срабатывает, когда |funding_rate| сравнивается с порогом percent.

    Args:
        condition_id: Уникальный идентификатор условия.
        direction: Направление сравнения ("<" или ">").
        percent: Пороговое значение в процентах.
        time_threshold_sec: Максимальное время до расчёта в секундах.
        interval: Интервал проверки в секундах.

    Attributes:
        time_threshold_sec: Максимальное время до расчёта в секундах.
        matched: Список сработавших условий в формате (symbol, rate_pct, secs_left).

    Note:
        direction:
            ">"  — |rate| >= percent   (больше или равно)
            "<"  — |rate| <= percent   (меньше или равно)
    """

    def __init__(
        self,
        condition_id: str,
        direction: str,
        percent: float,
        time_threshold_sec: int,
        interval: int,
    ) -> None:
        """Инициализирует FundingListener.

        Args:
            condition_id: Уникальный идентификатор условия.
            direction: Направление сравнения ("<" или ">").
            percent: Пороговое значение в процентах.
            time_threshold_sec: Максимальное время до расчёта в секундах.
            interval: Интервал проверки в секундах.

        Returns:
            None
        """
        super().__init__(
            condition_id=condition_id,
            direction=direction,
            percent=percent,
            interval=interval,
        )
        self.time_threshold_sec = time_threshold_sec
        self.matched: list[tuple[str, float, int]] = []

    @property
    def period_sec(self) -> int:
        return self.interval

    async def update_state(self, db_pool: asyncpg.Pool) -> None:
        """Заполняет self.matched свежими срабатываниями.

        Args:
            db_pool: Пул соединений с базой данных.

        Returns:
            None

        Raises:
            Exception: При ошибке работы с базой данных.
        """
        self.matched.clear()
        now = dt.datetime.now(dt.timezone.utc)

        try:
            async with db_pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT DISTINCT ON (symbol)
                           symbol,
                           funding_rate,
                           next_funding_ts
                      FROM funding_rate
                     WHERE next_funding_ts > $1  -- Исключаем устаревшие записи
                  ORDER BY symbol, ts DESC;
                    """,
                    now
                )
        except Exception as e:
            logger.error("Database error in update_state: %s", e)
            return

        for row in rows:
            try:
                funding_rate = row["funding_rate"]
                if funding_rate is None:
                    continue
                    
                rate_pct = float(funding_rate) * 100.0
                
                next_funding_ts = row["next_funding_ts"]
                if next_funding_ts is None:
                    continue
                
                secs_left = int((next_funding_ts - now).total_seconds())
                if secs_left < 0:
                    continue

                if self._trigger(abs(rate_pct)) and secs_left <= self.time_threshold_sec:
                    self.matched.append((row["symbol"], rate_pct, secs_left))
                    
            except (ValueError, TypeError, AttributeError) as e:
                logger.warning("Error processing funding row %s: %s", row, e)
                continue

    async def notify(self) -> None:
        """Отправляет алерты пользователям.

        Returns:
            None

        Raises:
            Exception: При ошибке отправки уведомления.
        """
        if not self.subscribers or not self.matched:
            return

        header = "[FUNDING]"
        for symbol, rate_pct, secs_left in self.matched:
            try:
                text = (
                    f"{header}\n"
                    f"{symbol.upper():7} {rate_pct:+.2f}% "
                    f"(до расчёта ≈ {secs_left} сек)"
                )
                await self.notify_subscribers(text)
            except Exception as e:
                logger.error("Error sending notification for %s: %s", symbol, e)

    def _trigger(self, abs_rate: float) -> bool:
        """Проверяет условие срабатывания.

        Args:
            abs_rate: Абсолютное значение funding rate в процентах.

        Returns:
            bool: True если условие сработало, False иначе.

        Raises:
            ValueError: При ошибке сравнения значений.
            TypeError: При неверном типе данных.
        """
        try:
            if self.direction == ">":
                return abs_rate >= self.percent
            elif self.direction == "<":
                return abs_rate <= self.percent
            else:
                logger.warning("Unknown direction: %s", self.direction)
                return False
        except (ValueError, TypeError):
            return False