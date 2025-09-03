import asyncio
import msgpack
import time
from typing import Dict, Set, List, Tuple
from fastapi import WebSocket
from config import logger
from modules.order.tracker.logic import order_densities

class DensityBroadcaster:
    """Транслирует данные о плотностях с поддержкой JSON и MessagePack."""
    
    def __init__(self):
        self.connections: Dict[WebSocket, str] = {}  # ws -> format ('json' или 'msgpack')
        self.last_snapshot: Dict = {}
        self._lock = asyncio.Lock()
        
    async def connect(self, websocket: WebSocket, format: str = "json"):
        """Подключает клиента с указанным форматом."""
        await websocket.accept()
        async with self._lock:
            self.connections[websocket] = format
        
        # Отправляем текущий snapshot
        snapshot = self._prepare_snapshot()
        message = {
            "type": "snapshot",
            "ts": int(time.time() * 1000),
            "data": list(snapshot.values())  # Для msgpack лучше список
        }
        
        await self._send_to_client(websocket, message, format)
        logger.info(f"[DENSITY_WS] Новое подключение ({format}), всего: {len(self.connections)}")
        
    async def _send_to_client(self, websocket: WebSocket, data: dict, format: str):
        """Отправляет данные в нужном формате."""
        try:
            if format == "msgpack":
                packed = msgpack.packb(data, use_bin_type=True)
                await websocket.send_bytes(packed)
            else:
                await websocket.send_json(data)
        except Exception as e:
            logger.debug(f"[DENSITY_WS] Ошибка отправки: {e}")
            await self.disconnect(websocket)
    
    async def broadcast_loop(self):
        """Основной цикл отправки обновлений."""
        while True:
            try:
                await asyncio.sleep(2)
                
                if not self.connections:
                    continue
                
                current = self._prepare_snapshot()
                delta = self._calculate_delta(self.last_snapshot, current)
                
                if delta['add'] or delta['update'] or delta['remove']:
                    message = {
                        "type": "delta",
                        "ts": int(time.time() * 1000),
                        "data": delta
                    }
                    
                    # Отправляем каждому в его формате
                    disconnected = []
                    for ws, format in list(self.connections.items()):
                        try:
                            await self._send_to_client(ws, message, format)
                        except:
                            disconnected.append(ws)
                    
                    # Удаляем отключенные
                    async with self._lock:
                        for ws in disconnected:
                            self.connections.pop(ws, None)
                
                self.last_snapshot = current
                
            except Exception as e:
                logger.error(f"[DENSITY_WS] Ошибка в broadcast_loop: {e}")
                await asyncio.sleep(5)
    
    def _prepare_snapshot(self) -> Dict[str, Dict]:
        """Готовит snapshot из order_densities."""
        result = {}
        
        for (symbol, order_type, price), density in order_densities.items():
            # Создаём уникальный ключ
            key = f"{symbol.upper()}:{order_type[0]}:{price}"
            
            # Вычисляем длительность в секундах
            duration_sec = int((time.time() * 1000 - density["first_seen"]) / 1000)
            
            result[key] = {
                "s": symbol.upper(),
                "t": "L" if order_type == "LONG" else "S",
                "p": price,
                "u": density["size_usd"],
                "pct": round(density["percent_from_market"], 2),
                "d": duration_sec
            }
        
        return result
    
    def _calculate_delta(self, old: Dict, new: Dict) -> Dict:
        """Вычисляет разницу между состояниями."""
        old_keys = set(old.keys())
        new_keys = set(new.keys())
        
        delta = {
            "add": [],
            "update": [],
            "remove": []
        }
        
        # Новые плотности
        for key in new_keys - old_keys:
            delta["add"].append(new[key])
        
        # Удалённые плотности (только ключи)
        delta["remove"] = list(old_keys - new_keys)
        
        # Изменённые плотности
        for key in old_keys & new_keys:
            old_item = old[key]
            new_item = new[key]
            
            # Проверяем изменения в размере или длительности
            if (abs(old_item["u"] - new_item["u"]) > 1000 or  # Изменение > $1000
                abs(old_item["d"] - new_item["d"]) > 10):     # Изменение > 10 сек
                delta["update"].append(new_item)
        
        return delta
    
    async def disconnect(self, websocket: WebSocket):
        """Отключает клиента."""
        async with self._lock:
            if websocket in self.connections:
                self.connections.pop(websocket, None)
                logger.info(f"[DENSITY_WS] Отключение, осталось: {len(self.connections)}")
    
    async def _safe_send(self, websocket: WebSocket, data: dict):
        """Безопасная отправка данных в websocket."""
        try:
            await websocket.send_json(data)
        except Exception as e:
            logger.debug(f"[DENSITY_WS] Ошибка отправки: {e}")
            await self.disconnect(websocket)
    
    async def _broadcast_to_all(self, message: dict):
        """Отправляет сообщение всем подключенным клиентам."""
        disconnected = set()
        
        for ws in list(self.connections):
            try:
                await ws.send_json(message)
            except:
                disconnected.add(ws)
        
        # Удаляем отключенные соединения
        async with self._lock:
            self.connections -= disconnected
        
        if disconnected:
            logger.info(f"[DENSITY_WS] Удалено {len(disconnected)} неактивных соединений")

broadcaster = DensityBroadcaster()