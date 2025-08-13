import asyncpg
from modules.listener import Listener

class VolumeAmountListener(Listener):
    """Слушатель абсолютного объёма торгов за временное окно.

    Отслеживает суммарный объём торгов по каждому торговому символу за заданный
    интервал времени и отправляет уведомления подписчикам при выполнении условий
    превышения или недостижения установленного порога.

    ВНИМАНИЕ: percent - в данном случае это не процент, а абсолютное значение объёма в USD
    """
    @property
    def period_sec(self) -> int:
        return self.interval

    async def update_state(self, db_pool: asyncpg.Pool) -> None:
        """Проверяет условия объёма и отправляет уведомления при их выполнении.

        Запрашивает из базы данных суммарный объём торгов за последнее временное окно
        для всех торговых символов. При выполнении установленного условия отправляет
        уведомления всем подписанным пользователям.

        Args:
            db_pool: Пул соединений с базой данных для выполнения запросов.
        """
        self.matched.clear()
        rows = await self._fetch_current_volumes(db_pool)

        for row in rows:
            cur_vol: float = float(row["cur_vol"])
            if self._trigger(cur_vol):
                self.matched.append((row["symbol"], cur_vol))

    async def notify(self) -> None:
        """Рассылает уведомления по self.matched"""
        if not self.subscribers or not self.matched:
            return
        for symbol, cur_vol in self.matched:
            direction = "превысил" if self.direction == ">" else "опустился ниже"
            text = (
                f"Объём {symbol} за {self.window_sec} с {direction} "
                f"{int(self.percent):,} USD\nФактический объём: {int(cur_vol):,} USD"
            )
            await self.notify_subscribers(text)

    async def _fetch_current_volumes(self, db_pool: asyncpg.Pool) -> list[asyncpg.Record]:
        """Запрашивает суммарный объём торгов по каждому символу за текущее окно.

        Выполняет SQL-запрос для получения суммарного объёма торгов за последний
        интервал времени, группируя данные по торговым символам.

        Args:
            db_pool: Пул соединений с базой данных.

        Returns:
            Список записей с полями 'symbol' и 'cur_vol', содержащих данные
            о текущем объёме торгов по каждому символу.
        """
        async with db_pool.acquire() as conn:
            return await conn.fetch(
                """
                WITH latest AS (
                    SELECT symbol, MAX(ts) AS max_ts
                    FROM volume
                    GROUP BY symbol
                ), cur AS (
                    SELECT v.symbol,
                           SUM(v.volume)::numeric AS cur_vol
                    FROM volume v
                    JOIN latest l USING (symbol)
                    WHERE v.ts > l.max_ts - $1 * INTERVAL '1 second'
                    GROUP BY v.symbol
                )
                SELECT symbol, cur_vol
                FROM cur;
                """,
                self.window_sec,
            )

    def _trigger(self, value: float) -> bool:
        """Проверяет выполнение условия сравнения объёма с пороговым значением.

        Args:
            value: Текущее значение объёма торгов для проверки.

        Returns:
            True, если условие выполнено (объём больше или меньше порога в зависимости
            от направления), иначе False.
        """
        return value >= self.percent if self.direction == ">" else value <= self.percent
