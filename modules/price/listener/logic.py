import asyncpg
from modules.listener import Listener

class PriceListener(Listener):
    """
    Лисенер изменения цены
    """
    async def update_state(self, db_pool: asyncpg.Pool) -> None:
        """Обновляет список подходящих тикеров.

        Записывает пары (symbol, change_pct) в self.matched
        """
        self.matched.clear()
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                WITH latest AS (
                    SELECT DISTINCT ON (p.symbol)
                        p.symbol,
                        p.price AS current_price,
                        p.ts     AS current_ts
                    FROM price AS p
                    ORDER BY p.symbol, p.ts DESC
                ),
                past AS (
                    SELECT DISTINCT ON (pr.symbol)
                        pr.symbol,
                        pr.price AS past_price
                    FROM price AS pr
                    JOIN latest AS l ON l.symbol = pr.symbol
                    WHERE pr.ts <= l.current_ts - $1 * INTERVAL '1 second'
                    ORDER BY pr.symbol, pr.ts DESC
                )
                SELECT l.symbol,
                    l.current_price,
                    p.past_price
                FROM latest AS l
                JOIN past AS p ON p.symbol = l.symbol;
                """,
                self.interval,
            )
        if not rows:
            return
        for row in rows:
            if self._trigger(row["current_price"], row["past_price"]):
                change = ((row["current_price"] - row["past_price"]) / row["past_price"]) * 100
                self.matched.append((row["symbol"], change))


    async def notify(self) -> None:
        """Рассылает уведомления по self.matched и очищает список."""
        if not self.subscribers or not self.matched:
            return
        for symbol, change in self.matched:
            direction = "выросла" if change > 0 else "упала"
            text = (f"Цена {symbol} {direction} на {abs(change):.2f}% "
                    f"за {self.interval} сек.")
            await self.notify_subscribers(text)

    def _trigger(self, current: float, past: float) -> bool:
        """
        Проверяет выполнение условия изменения цены:
        - Если direction == '>', алерт если изменение > percent или < -percent
        - Если direction == '<', алерт если изменение в диапазоне [-percent, percent]
        """
        if past == 0:
            return False
        change = ((current - past) / past) * 100
        if self.direction == ">":
            return change > self.percent or change < -self.percent
        elif self.direction == "<":
            return -self.percent <= change <= self.percent
        return False
