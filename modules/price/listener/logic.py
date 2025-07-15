import asyncpg
from typing import List
from bot.settings import bot

class Listener:
    """
    Класс для отслеживания одного уникального условия изменения цены и уведомления подписчиков.

    Args:
        condition_id (str): Уникальный идентификатор условия.
        percent (float): Процент изменения цены (например, 5.0).
        interval (int): Интервал в секундах (например, 60).
        subscribers (List[int]): Список Telegram‑ID пользователей, подписанных на это условие.
    """
    def __init__(self, condition_id: str, percent: float, interval: int) -> None:
        self.condition_id = condition_id
        self.percent = percent
        self.interval = interval
        self.subscribers: List[int] = []

    def get_condition_id(self) -> str:
        """Возвращает уникальный идентификатор условия.
        
        Returns:
            str: Уникальный идентификатор условия.
        """
        return self.condition_id

    def add_subscriber(self, user_id: int) -> None:
        """Регистрирует пользователя в списке подписчиков.

        Пользователь добавляется только один раз; повторные вызовы с тем же
        user_id игнорируются.

        Args:
            user_id (int): Telegram‑ID пользователя.
        """
        if user_id not in self.subscribers:
            self.subscribers.append(user_id)

    def remove_subscriber(self, user_id: int) -> None:
        """Удаляет пользователя из списка подписчиков.

        Если ``user_id`` отсутствует в списке, метод ничего не делает.

        Args:
            user_id (int): Telegram‑ID пользователя.
        """
        if user_id in self.subscribers:
            self.subscribers.remove(user_id)

    async def notify_subscribers(self, text: str) -> None:
        """Отправляет текстовое уведомление каждому подписчику.

        Args:
            text (str): Готовое сообщение для рассылки.
        """
        for user_id in self.subscribers:
            print(f"Alert for user {user_id}: {text}")
            await bot.send_message(user_id, text)

    async def check_and_notify(self, db_pool: asyncpg.Pool) -> None:
        """Проверяет изменение цены и при необходимости отправляет оповещение.

        Алгоритм:

        1. Извлекает из БД последнюю цену (current_price) для каждого тикера.
        2. Находит цену этого же тикера `interval` секунд назад (past_price).
        3. Сравнивает относительное изменение с порогом percent.
        4. Формирует и рассылает уведомление подписчикам, если условие
           выполняется.

        Args:
            db_pool (asyncpg.Pool): Пул соединений с базой данных PostgreSQL,
                содержащей таблицу price.
        """
        if not self.subscribers:
            return

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
            change = self._calc_percent_change(row["current_price"], row["past_price"])
            if change >= self.percent:
                direction = "выросла" if row["current_price"] > row["past_price"] else "упала"
                message = (
                    f"Цена {row['symbol']} {direction} на {change:.2f}% "
                    f"за {self.interval} секунд."
                )
                await self.notify_subscribers(message)

    @staticmethod
    def _calc_percent_change(current: float, past: float) -> float:
        """Вычисляет модуль процентного изменения между двумя ценами.

        Args:
            current (float): Текущая (более свежая) цена.
            past (float): Цена во временной точке ``interval`` секунд назад.

        Returns:
            float: Положительное процентное изменение (0.0, если ``past`` == 0).
        """
        if past == 0:
            return 0.0
        return abs((current - past) / past) * 100

