from typing import List

class Listener:
    """
    Базовый класс для всех слушателей.

    Args:
        condition_id (str): Уникальный идентификатор условия.
        direction (str): Направление изменения ('>' или '<').
        percent (float): Процент изменения цены (например, 5.0).
        interval (int): Интервал в секундах (например, 60).
        window_sec (int | None): Длина окна расчёта, сек. Если не задано - считается равным `interval` (поведение как раньше)
        matched (list[tuple[str, float]]): Список подходящих тикеров.
        subscribers (List[int]): Список Telegram‑ID пользователей, подписанных на это условие.
    """
    def __init__(self, condition_id: str, direction: str, percent: float, interval: int, window_sec: int | None = None) -> None:
        self.condition_id = condition_id
        self.direction = direction
        self.percent = percent
        self.interval = interval
        self.window_sec: int = window_sec if window_sec is not None else interval
        self.matched: list[tuple[str, float]] = []
        self.subscribers: List[int] = []

    @property
    def period_sec(self) -> int:
        """Интервал между обновлениями состояния этого слушателя.

        Должен быть переопределён наследником.
        """
        raise NotImplementedError

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

# закоменчено чтобы потестить весокеты, т.к начинает ругаться на то что токен бота неправильный
# хотя в целом это можно нахуй выпилить ибо это не используется, но пока оставлю 
    # async def notify_subscribers(self, text: str) -> None:
    #     """Отправляет текстовое уведомление каждому подписчику.

    #     Args:
    #         text (str): Готовое сообщение для рассылки.
    #     """
    #     from bot.settings import bot
    #     for user_id in self.subscribers:
    #         print(f"Alert for user {user_id}: {text}")
    #         await bot.send_message(user_id, text)

    def matched_symbol_only(self) -> set[str]:
        """Вернёт множество тикеров независимо от формата matched."""
        return {item[0] for item in self.matched}

    async def stop(self) -> None:
        """
        Останавливает слушатель и освобождает ресурсы.
        
        Этот метод должен быть переопределён наследниками для корректной
        остановки слушателя и освобождения ресурсов (соединения с БД,
        активные задачи, таймеры и т.д.).
        
        Returns:
            None
        """
        self.subscribers.clear()
        self.matched.clear()

