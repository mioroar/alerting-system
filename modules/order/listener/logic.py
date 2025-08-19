# from modules.manager import BaseListenerManager
# from modules.order.listener.logic import OrderListener


# class OrderListenerManager(BaseListenerManager[OrderListener]):
#     """Менеджер для OrderListener.
    
#     Управляет жизненным циклом слушателей плотности ордеров,
#     обеспечивает создание, обновление и удаление OrderListener экземпляров.
#     Переопределяет методы для корректной работы с тремя параметрами order.
#     """
    
#     def __init__(self) -> None:
#         """Инициализирует менеджер с типом OrderListener."""
#         super().__init__(OrderListener)

#     def get_condition_id(self, params: dict) -> str:
#         """Генерирует уникальный ID условия для order-слушателя.

#         Для order учитываются: direction, size_usd, max_percent, min_duration.

#         Args:
#             params (dict): Параметры слушателя.

#         Returns:
#             str: Уникальный идентификатор.
#         """
#         key_fields = [
#             ("direction", params["direction"]),
#             ("size_usd", params.get("size_usd", params.get("percent", 0))),
#             ("max_percent", params.get("max_percent", 0)),
#             ("min_duration", params.get("min_duration", 0)),
#         ]
        
#         return str(hash(tuple(key_fields)))

#     async def add_listener(
#         self,
#         params: dict,
#         user_id: int | None = None,
#     ) -> OrderListener:
#         """Создает или возвращает OrderListener с заданными параметрами.

#         Args:
#             params (dict): Параметры слушателя:
#                 - direction (str): '>' или '<'
#                 - size_usd (float): Пороговое значение размера в USD
#                 - max_percent (float): Максимальное отклонение от цены
#                 - min_duration (int): Минимальная длительность в секундах
#                 - interval (int, optional): Интервал проверки (по умолчанию 60)
#             user_id (int | None): ID пользователя для подписки.

#         Returns:
#             OrderListener: Экземпляр слушателя.
#         """
#         # Извлекаем параметры для order
#         size_usd = params.get("size_usd", params.get("percent", 1000000))
#         max_percent = params.get("max_percent", 5.0)
#         min_duration = params.get("min_duration", 300)
        
#         # Обновляем params для корректной работы базового класса
#         order_params = {
#             "direction": params["direction"],
#             "percent": size_usd,  # Используем как временное значение
#             "interval": params.get("interval", 60),
#             "window_sec": params.get("window_sec", 60),
#             "size_usd": size_usd,
#             "max_percent": max_percent,
#             "min_duration": min_duration,
#         }
        
#         # Вызываем базовый метод
#         listener = await super().add_listener(order_params, user_id)
        
#         # Устанавливаем специфичные для order параметры
#         listener.set_order_params(size_usd, max_percent, min_duration)
        
#         return listener


# # Глобальный экземпляр менеджера
# order_listener_manager = OrderListenerManager()


# async def get_order_listener_manager() -> OrderListenerManager:
#     """Возвращает глобальный экземпляр OrderListenerManager.

#     Обеспечивает единственность менеджера для всего приложения.

#     Returns:
#         OrderListenerManager: Глобальный экземпляр менеджера для order-слушателей.
#     """
#     return order_listener_manager