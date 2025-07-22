from modules.manager import BaseListenerManager
from modules.price.listener.logic import PriceListener

class PriceListenerManager(BaseListenerManager[PriceListener]):
    """Менеджер для PriceListener."""
    def __init__(self) -> None:
        super().__init__(PriceListener)


price_listener_manager = PriceListenerManager()

async def get_price_listener_manager() -> PriceListenerManager:
    """Возвращает (и при необходимости создаёт) глобальный ListenerManager.

    Returns:
        ListenerManager: Глобальный экземпляр менеджера.
    """
    return price_listener_manager