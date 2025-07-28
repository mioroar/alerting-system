import asyncpg
from typing import Final, Tuple

from modules.listener import Listener
from modules.oi.config import OI_HISTORY_PERIOD_SEC

__all__ = ["OIListener"]


class OIListener(Listener):
    """Отслеживает Δ% между текущим OI и медианой за 24 ч."""

    _HUMAN_SUFFIXES: Final[tuple[tuple[int, str], ...]] = (
        (1_000_000_000, "b"),
        (1_000_000, "m"),
        (1_000, "k"),
    )

    def __init__(
        self,
        condition_id: str,
        direction: str,
        percent: float,
        interval: int | None = None,
    ) -> None:
        """Инициализирует слушатель OI.

        Args:
            condition_id: Уникальный идентификатор условия.
            direction: Направление сравнения ('>' или '<').
            percent: Процентное значение для срабатывания.
            interval: Интервал проверки в секундах (по умолчанию 60).
        """
        super().__init__(condition_id, direction, percent, interval or 60)
        self.matched: list[Tuple[str, float, float]] = []

    async def update_state(self, db_pool: asyncpg.Pool) -> None:
        """Обновляет состояние слушателя свежими данными из БД.

        Выполняет SQL-запрос для получения текущего OI и медианы за исторический
        период, затем проверяет условия срабатывания для каждого символа.

        Args:
            db_pool: Пул соединений с базой данных.
        """
        self.matched.clear()
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                WITH latest AS (
                    SELECT DISTINCT ON (o.symbol)
                           o.symbol,
                           o.open_interest  AS current_oi,
                           o.ts             AS current_ts
                      FROM open_interest o
                  ORDER BY o.symbol, o.ts DESC
                ),
                hist AS (
                    SELECT o.symbol,
                           percentile_cont(0.5)
                               WITHIN GROUP (ORDER BY o.open_interest) AS median_oi
                      FROM open_interest o
                      JOIN latest l USING (symbol)
                     WHERE o.ts >= l.current_ts - $1 * INTERVAL '1 second'
                  GROUP BY o.symbol
                )
                SELECT l.symbol, l.current_oi, h.median_oi
                  FROM latest l
                  JOIN hist   h USING (symbol);
                """,
                OI_HISTORY_PERIOD_SEC,
            )
        for row in rows:
            median: float = float(row["median_oi"] or 0)
            if median == 0:
                continue
            change_pct = (float(row["current_oi"]) / median - 1.0) * 100.0
            if self._trigger(change_pct):
                self.matched.append(
                    (row["symbol"], change_pct, float(row["current_oi"]))
                )

    async def notify(self) -> None:
        """Отправляет уведомления подписчикам о сработавших условиях.

        Формирует текстовые сообщения для каждого сработавшего символа
        и отправляет их всем подписчикам.
        """
        if not self.subscribers or not self.matched:
            return
        for symbol, change_pct, current_oi in self.matched:
            text = (
                f"[OI] {symbol}: {change_pct:+.2f}% от медианы "
                f"(OI ≈ {self._human(current_oi)}$)"
            )
            await self.notify_subscribers(text)

    def _trigger(self, change_pct: float) -> bool:
        """Проверяет условие срабатывания на основе процентного изменения.

        Args:
            change_pct: Процентное изменение OI относительно медианы.

        Returns:
            True если условие сработало, False в противном случае.
        """
        if self.direction == ">":
            return change_pct >= self.percent
        if self.direction == "<":
            return abs(change_pct) <= self.percent
        return False

    @classmethod
    def _human(cls, value: float) -> str:
        """Форматирует числовое значение в человекочитаемый вид.

        Преобразует большие числа в формат с суффиксами k (тысячи),
        m (миллионы), b (миллиарды).

        Args:
            value: Числовое значение для форматирования.

        Returns:
            Отформатированная строка с суффиксом.
        """
        for divisor, suffix in cls._HUMAN_SUFFIXES:
            if abs(value) >= divisor:
                return f"{value / divisor:.2f}{suffix}"
        return f"{value:.2f}"
