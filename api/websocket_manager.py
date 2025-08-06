import json
import asyncio
from typing import Dict, Set
from fastapi import WebSocket
from fastapi.websockets import WebSocketState
from config import logger


class WebSocketManager:
    """Менеджер WebSocket соединений для алертов.
    
    Обеспечивает управление WebSocket соединениями пользователей для отправки
    алертов в реальном времени. Поддерживает одно соединение на пользователя.
    Реализует паттерн Singleton для обеспечения единственного экземпляра.
    
    Attributes:
        _instance: Единственный экземпляр менеджера (Singleton).
        _connections: Словарь активных WebSocket соединений по user_id.
        _lock: Асинхронная блокировка для потокобезопасности.
    """
    
    _instance = None
    
    def __init__(self):
        """Инициализирует менеджер WebSocket соединений."""
        self._connections: Dict[int, WebSocket] = {}
        self._lock = asyncio.Lock()
    
    @classmethod
    def instance(cls) -> "WebSocketManager":
        """
        Возвращает (и при необходимости создаёт) экземпляр менеджера.

        Returns:
            WebSocketManager: Экземпляр менеджера.
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    async def _safe_close_websocket(self, websocket: WebSocket, user_id: int) -> None:
        """Безопасно закрывает WebSocket соединение.
        
        Проверяет состояние соединения и закрывает его с обработкой ошибок.
        
        Args:
            websocket: WebSocket соединение для закрытия.
            user_id: Идентификатор пользователя для логирования.
        """
        try:
            if websocket.client_state == WebSocketState.CONNECTED:
                await websocket.close()
        except Exception as exc:
            logger.warning(f"[WS] Ошибка закрытия соединения {user_id}: {exc}")
    
    async def connect(self, websocket: WebSocket, user_id: int) -> None:
        """Подключает пользователя к WebSocket.
        
        Принимает новое WebSocket соединение и связывает его с пользователем.
        Если у пользователя уже есть активное соединение, оно закрывается.
        
        Args:
            websocket: WebSocket соединение для подключения.
            user_id: Уникальный идентификатор пользователя.
            
        Raises:
            Exception: При ошибке закрытия старого соединения.
        """
        await websocket.accept()
        
        async with self._lock:
            if user_id in self._connections:
                old_ws = self._connections[user_id]
                await self._safe_close_websocket(old_ws, user_id)
            
            self._connections[user_id] = websocket
        
        logger.info(f"[WS] Пользователь {user_id} подключен")
    
    async def disconnect(self, user_id: int) -> None:
        """Отключает пользователя от WebSocket.
        
        Закрывает соединение пользователя и удаляет его из списка активных
        соединений.
        
        Args:
            user_id: Уникальный идентификатор пользователя для отключения.
            
        Raises:
            Exception: При ошибке закрытия соединения.
        """
        async with self._lock:
            websocket = self._connections.pop(user_id, None)
            if websocket:
                await self._safe_close_websocket(websocket, user_id)
        
        logger.info(f"[WS] Пользователь {user_id} отключен")
    
    async def send_alert(self, user_id: int, alert_data: dict) -> bool:
        """Отправляет алерт конкретному пользователю.
        
        Сериализует данные алерта в JSON и отправляет через WebSocket.
        Автоматически удаляет неактивные соединения.
        
        Args:
            user_id: Уникальный идентификатор пользователя.
            alert_data: Словарь с данными алерта для отправки.
            
        Returns:
            bool: True если алерт успешно отправлен, False в противном случае.
            
        Raises:
            Exception: При ошибке сериализации или отправки данных.
        """
        async with self._lock:
            websocket = self._connections.get(user_id)
        
        if not websocket:
            logger.debug(f"[WS] Пользователь {user_id} не подключен")
            return False
            
        if websocket.client_state != WebSocketState.CONNECTED:
            logger.debug(f"[WS] Соединение с пользователем {user_id} не активно")
            async with self._lock:
                self._connections.pop(user_id, None)
            return False
        
        try:
            await websocket.send_text(json.dumps(alert_data, ensure_ascii=False))
            logger.debug(f"[WS] Алерт отправлен пользователю {user_id}")
            return True
        except Exception as exc:
            logger.exception(f"[WS] Ошибка отправки пользователю {user_id}: {exc}")
            async with self._lock:
                self._connections.pop(user_id, None)
            return False
    
    async def broadcast_alert(self, user_ids: Set[int], alert_data: dict) -> int:
        """Отправляет алерт группе пользователей.
        
        Параллельно отправляет алерт всем указанным пользователям и возвращает
        количество успешно доставленных сообщений.
        
        Args:
            user_ids: Множество идентификаторов пользователей для отправки.
            alert_data: Словарь с данными алерта для отправки.
            
        Returns:
            int: Количество успешно доставленных сообщений.
            
        Raises:
            Exception: При ошибке отправки сообщений пользователям.
        """
        if not user_ids:
            return 0
            
        tasks = []
        for user_id in user_ids:
            tasks.append(self.send_alert(user_id, alert_data))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        successful = sum(1 for r in results if r is True)
        
        logger.info(f"[WS] Алерт отправлен {successful}/{len(tasks)} пользователям")
        return successful
    
    def get_connected_users(self) -> Set[int]:
        """Получает список подключенных пользователей.
        
        Returns:
            Set[int]: Множество идентификаторов подключенных пользователей.
        """
        return set(self._connections.keys())
    
    def is_connected(self, user_id: int) -> bool:
        """Проверяет подключен ли пользователь.
        
        Args:
            user_id: Уникальный идентификатор пользователя для проверки.
            
        Returns:
            bool: True если пользователь подключен и соединение активно.
        """
        websocket = self._connections.get(user_id)
        return (websocket is not None and 
                websocket.client_state == WebSocketState.CONNECTED)
    
    async def send_message(self, user_id: int, message_type: str, data: dict) -> bool:
        """Отправляет произвольное сообщение пользователю.
        
        Формирует сообщение с указанным типом и данными, затем отправляет
        через WebSocket соединение.
        
        Args:
            user_id: Уникальный идентификатор пользователя.
            message_type: Тип сообщения для включения в payload.
            data: Словарь с данными сообщения.
            
        Returns:
            bool: True если сообщение успешно отправлено, False в противном случае.
        """
        message = {
            "type": message_type,
            **data
        }
        return await self.send_alert(user_id, message)
    
    def get_stats(self) -> dict:
        """Получает статистику WebSocket соединений.
        
        Returns:
            dict: Словарь со статистикой соединений:
                - total_connections: Общее количество соединений
                - active_connections: Количество активных соединений
                - inactive_connections: Количество неактивных соединений
        """
        total_connections = len(self._connections)
        active_connections = sum(
            1 for ws in self._connections.values() 
            if ws.client_state == WebSocketState.CONNECTED
        )
        
        return {
            "total_connections": total_connections,
            "active_connections": active_connections,
            "inactive_connections": total_connections - active_connections
        }


