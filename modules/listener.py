from typing import List

from bot.settings import bot

class Listener:
    """
    Базовый класс для всех слушателей.

    Args:
        condition_id (str): Уникальный идентификатор условия.
        direction (str): Направление изменения ('>' или '<').
        percent (float): Процент изменения цены (например, 5.0).
        interval (int): Интервал в секундах (например, 60).
        matched (list[tuple[str, float]]): Список подходящих тикеров.
        subscribers (List[int]): Список Telegram‑ID пользователей, подписанных на это условие.
    """
    def __init__(self, condition_id: str, direction: str, percent: float, interval: int) -> None:
        self.condition_id = condition_id
        self.direction = direction
        self.percent = percent
        self.interval = interval
        self.matched: list[tuple[str, float]] = []
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

