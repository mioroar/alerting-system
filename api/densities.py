from config import logger
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from .density_broadcaster import broadcaster

router = APIRouter()

@router.websocket("/ws/densities")
async def websocket_densities(
    websocket: WebSocket,
    format: str = Query("json", regex="^(json|msgpack)$")
):
    """WebSocket endpoint с поддержкой JSON и MessagePack."""
    await broadcaster.connect(websocket, format)
    try:
        while True:
            # Держим соединение
            if format == "msgpack":
                data = await websocket.receive_bytes()
                # Распаковываем ping
                if data == b'ping':
                    await websocket.send_bytes(b'pong')
            else:
                data = await websocket.receive_text()
                if data == "ping":
                    await websocket.send_text("pong")
    except:
        pass
    finally:
        await broadcaster.disconnect(websocket)

@router.get("/densities/stats")
async def get_densities_stats():
    """Получить статистику по плотностям."""
    from modules.order.tracker.logic import order_densities
    
    total = len(order_densities)
    by_type = {"LONG": 0, "SHORT": 0}
    by_size = {"small": 0, "medium": 0, "large": 0}
    by_status = {"normal": 0, "touched": 0}
    
    for (symbol, price), density in order_densities.items():
        # Получаем order_type из самого объекта density
        order_type = density["order_type"]
        by_type[order_type] += 1
        
        size = density["current_size_usd"]  # Обновлено поле
        if size < 500_000:
            by_size["small"] += 1
        elif size < 1_000_000:
            by_size["medium"] += 1
        else:
            by_size["large"] += 1
        
        # Статистика по статусу "тронутости"
        if density["touched"] and density["reduction_usd"] > 0:
            by_status["touched"] += 1
        else:
            by_status["normal"] += 1
    
    return {
        "total": total,
        "by_type": by_type,
        "by_size": by_size,
        "by_status": by_status,
        "connected_clients": len(broadcaster.connections)
    }