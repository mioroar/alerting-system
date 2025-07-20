from __future__ import annotations

import asyncpg
from typing import List

from bot.settings import bot


class VolumeAmountListener:
    """Слушатель абсолютного объёма торгов за временное окно.

    Отслеживает суммарный объём торгов по каждому торговому символу за заданный
    интервал времени и отправляет уведомления подписчикам при выполнении условий
    превышения или недостижения установленного порога.

    Attributes:
        _condition_id: Уникальный идентификатор условия.
        amount: Пороговое значение объёма в USD для сравнения.
        interval: Длительность временного окна в секундах.
        direction: Направление сравнения ('>' или '<').
        subscribers: Список идентификаторов подписанных пользователей.
    """

    def __init__(self, condition_id: str, amount: float, interval: int, direction: str) -> None:
        """Инициализирует слушатель объёма торгов.

        Args:
            condition_id: Уникальный хеш-идентификатор условия.
            amount: Пороговое значение объёма в USD (например, 10_000_000).
            interval: Длительность временного окна в секундах для суммирования объёма.
            direction: Направление проверки условия – '>' для превышения или '<' для недостижения.
        """
        self._condition_id: str = condition_id
        self.amount: float = amount
        self.interval: int = interval
        self.direction: str = direction
        self.subscribers: List[int] = []

    def get_condition_id(self) -> str:
        """Возвращает уникальный идентификатор условия.

        Returns:
            Строковый идентификатор условия слушателя.
        """
        return self._condition_id

    def add_subscriber(self, user_id: int) -> None:
        """Добавляет пользователя в список подписчиков на уведомления.

        Если пользователь уже подписан, повторное добавление игнорируется.

        Args:
            user_id: Идентификатор пользователя для подписки на уведомления.
        """
        if user_id not in self.subscribers:
            self.subscribers.append(user_id)

    def remove_subscriber(self, user_id: int) -> None:
        """Удаляет пользователя из списка подписчиков.

        Если пользователь не был подписан, операция игнорируется.

        Args:
            user_id: Идентификатор пользователя для отписки от уведомлений.
        """
        if user_id in self.subscribers:
            self.subscribers.remove(user_id)

    async def check_and_notify(self, db_pool: asyncpg.Pool) -> None:
        """Проверяет условия объёма и отправляет уведомления при их выполнении.

        Запрашивает из базы данных суммарный объём торгов за последнее временное окно
        для всех торговых символов. При выполнении установленного условия отправляет
        уведомления всем подписанным пользователям.

        Args:
            db_pool: Пул соединений с базой данных для выполнения запросов.
        """
        if not self.subscribers:
            return

        rows = await self._fetch_current_volumes(db_pool)

        for row in rows:
            cur_vol: float = float(row["cur_vol"])
            if self._trigger(cur_vol):
                await self._notify(
                    f"Объём {row['symbol']} за {self.interval} с "
                    f"{'превысил' if self.direction == '>' else 'опустился ниже'} "
                    f"{self.amount:,.0f} USD.\n"
                    f"Фактический объём: {cur_vol:,.0f} USD"
                )

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
                self.interval,
            )

    def _trigger(self, value: float) -> bool:
        """Проверяет выполнение условия сравнения объёма с пороговым значением.

        Args:
            value: Текущее значение объёма торгов для проверки.

        Returns:
            True, если условие выполнено (объём больше или меньше порога в зависимости
            от направления), иначе False.
        """
        return value >= self.amount if self.direction == ">" else value <= self.amount

    async def _notify(self, text: str) -> None:
        """Отправляет текстовое уведомление всем подписанным пользователям.

        Args:
            text: Текст сообщения для отправки подписчикам.
        """
        for uid in self.subscribers:
            await bot.send_message(uid, text)
