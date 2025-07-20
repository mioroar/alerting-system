import asyncpg
from typing import List

from bot.settings import bot


class VolumeChangeListener:
    """Следит за относительным изменением суммы объёма за два соседних окна.

    Класс отслеживает изменения объёма торгов для различных торговых символов
    и уведомляет подписчиков при превышении заданного порога изменения.

    Attributes:
        percent (float): Порог изменения в процентах.
        interval (int): Длина окна в секундах.
        direction (str): Направление отслеживания ('>' для роста, '<' для падения).
        subscribers (List[int]): Список ID пользователей-подписчиков.
    """

    def __init__(
        self, condition_id: str, percent: float, interval: int, direction: str
    ) -> None:
        """Инициализирует объект VolumeChangeListener.

        Args:
            condition_id (str): Уникальный идентификатор условия.
            percent (float): Порог изменения в процентах.
            interval (int): Длина окна в секундах.
            direction (str): Направление отслеживания ('>' для роста, '<' для падения).
        """
        self._condition_id: str = condition_id
        self.percent: float = percent
        self.interval: int = interval
        self.direction: str = direction
        self.subscribers: List[int] = []

    def get_condition_id(self) -> str:
        """Возвращает уникальный идентификатор условия.

        Returns:
            str: Уникальный идентификатор условия.
        """
        return self._condition_id

    def add_subscriber(self, user_id: int) -> None:
        """Добавляет пользователя в список подписчиков.

        Args:
            user_id (int): ID пользователя для добавления в подписку.
        """
        if user_id not in self.subscribers:
            self.subscribers.append(user_id)

    def remove_subscriber(self, user_id: int) -> None:
        """Удаляет пользователя из списка подписчиков.

        Args:
            user_id (int): ID пользователя для удаления из подписки.
        """
        if user_id in self.subscribers:
            self.subscribers.remove(user_id)

    async def check_and_notify(self, db_pool: asyncpg.Pool) -> None:
        """Проверяет условия изменения объёма и уведомляет подписчиков.

        Выполняет SQL-запрос для получения данных об объёмах торгов за два
        соседних временных окна, вычисляет относительное изменение и отправляет
        уведомления подписчикам при срабатывании условий.

        Args:
            db_pool (asyncpg.Pool): Пул соединений с базой данных PostgreSQL.
        """
        if not self.subscribers:
            return

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
                self.interval,
            )

        for row in rows:
            change = self._relative_change(
                float(row["cur_vol"]), float(row["prev_vol"])
            )
            if self._trigger(change):
                text = (
                    f"Объём {row['symbol']} за последние {self.interval} с "
                    f"{'вырос' if change > 0 else 'упал'} на {abs(change):.2f} %."
                    f"\nТекущий объём: {row['cur_vol']}"
                    f"\nПрошлый объём: {row['prev_vol']}"
                )
                await self._notify_subscribers(text)

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

    async def _notify_subscribers(self, text: str) -> None:
        """Отправляет уведомление всем подписчикам.

        Args:
            text (str): Текст уведомления для отправки.
        """
        for user_id in self.subscribers:
            await bot.send_message(user_id, text)

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
