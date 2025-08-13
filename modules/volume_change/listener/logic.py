import asyncpg
from modules.listener import Listener

class VolumeChangeListener(Listener):
    """Следит за относительным изменением суммы объёма за два соседних окна.

    Класс отслеживает изменения объёма торгов для различных торговых символов
    и уведомляет подписчиков при превышении заданного порога изменения.
    """
    @property
    def period_sec(self) -> int:
        return self.interval

    async def update_state(self, db_pool: asyncpg.Pool) -> None:
        """Проверяет условия изменения объёма и уведомляет подписчиков.

        Выполняет SQL-запрос для получения данных об объёмах торгов за два
        соседних временных окна, вычисляет относительное изменение и отправляет
        уведомления подписчикам при срабатывании условий.

        Args:
            db_pool (asyncpg.Pool): Пул соединений с базой данных PostgreSQL.
        """
        self.matched.clear()
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                WITH latest AS (
                    SELECT symbol, MAX(ts) AS max_ts
                    FROM volume
                    GROUP BY symbol
                ),
                cur AS (
                    SELECT v.symbol,
                           SUM(v.volume)::numeric AS cur_vol
                    FROM volume v
                    JOIN latest l USING (symbol)
                    WHERE v.ts > l.max_ts - $1 * INTERVAL '1 second'
                    GROUP BY v.symbol
                ),
                prev AS (
                    SELECT v.symbol,
                           SUM(v.volume)::numeric AS prev_vol
                    FROM volume v
                    JOIN latest l USING (symbol)
                    WHERE v.ts > l.max_ts - 2*$1 * INTERVAL '1 second'
                      AND v.ts <= l.max_ts - $1 * INTERVAL '1 second'
                    GROUP BY v.symbol
                )
                SELECT c.symbol,
                       c.cur_vol,
                       p.prev_vol
                FROM cur c
                JOIN prev p USING (symbol);
                """,
                self.window_sec,
            )

        for row in rows:
            change = self._relative_change(
                float(row["cur_vol"]), float(row["prev_vol"])
            )
            if self._trigger(change):
                self.matched.append((row["symbol"], change))

    async def notify(self) -> None:
        """Рассылает уведомления по self.matched"""
        if not self.subscribers or not self.matched:
            return
        for symbol, change in self.matched:
            direction = "вырос" if change > 0 else "упал"
            text = (f"Объём {symbol} {direction} на {abs(change):.2f} % за {self.window_sec}с")
            await self.notify_subscribers(text)

    def _trigger(self, change: float) -> bool:
        """Проверяет, выполняется ли условие срабатывания с учётом направления.

        Args:
            change (float): Относительное изменение объёма в процентах.

        Returns:
            bool: True, если условие срабатывания выполнено, False в противном случае.
        """
        if self.direction == ">":
            return change >= self.percent
        return change <= -self.percent

    @staticmethod
    def _relative_change(current: float, past: float) -> float:
        """Вычисляет знак-сохраняющее относительное изменение в процентах.

        Args:
            current (float): Текущее значение.
            past (float): Предыдущее значение.

        Returns:
            float: Относительное изменение в процентах. Возвращает 0.0, если 
                   предыдущее значение равно нулю.
        """
        if past == 0:
            return 0.0
        return (current - past) / past * 100
