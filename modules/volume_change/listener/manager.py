from modules.manager import BaseListenerManager
from modules.volume_change.listener.logic import VolumeChangeListener


class VolumeChangeListenerManager(BaseListenerManager[VolumeChangeListener]):
    """Менеджер для VolumeChangeListener."""
    def __init__(self) -> None:
        super().__init__(VolumeChangeListener)


volume_change_listener_manager = VolumeChangeListenerManager()

async def get_volume_change_listener_manager() -> VolumeChangeListenerManager:
    """Возвращает экземпляр синглтона менеджера слушателей изменения процента объёма.
    
    Returns:
        VolumeChangeListenerManager: Глобальный экземпляр менеджера слушателей.
    """
    return volume_change_listener_manager
