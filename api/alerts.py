from typing import List
from fastapi import APIRouter, HTTPException

from modules.composite.manager import CompositeListenerManager
from modules.composite.utils import parse_expression
from .websocket_manager import WebSocketManager
from .schemas import AlertRequest, AlertResponse

router = APIRouter()

@router.get("/alerts", response_model=List[AlertResponse])
async def get_alerts(user_id: int):
    """Получение всех алертов пользователя
    
    Args:
        user_id (int): Telegram‑ID пользователя.

    Returns:
        List[AlertResponse]: Список всех алертов пользователя.
    """
    user_subscriptions = (
        CompositeListenerManager.instance().get_user_subscriptions(user_id)
    )

    return [
        AlertResponse(
            alert_id=alert_id,
            expression=sub.readable_expression,
            subscribers_count=len(sub.subscribers),
            is_websocket_connected=WebSocketManager.instance().is_connected(user_id)
        )
        for alert_id, sub in user_subscriptions.items()
    ]

@router.get("/alerts/all", response_model=List[AlertResponse])
async def get_all_alerts():
    """Получение всех алертов в системе
    
    Returns:
        List[AlertResponse]: Список всех алертов.
    """
    all_alerts = CompositeListenerManager.instance().all_alerts
    
    return [
        AlertResponse(
            alert_id=alert_id,
            expression=sub.readable_expression,
            subscribers_count=len(sub.subscribers),
            is_websocket_connected=any(
                WebSocketManager.instance().is_connected(user_id) 
                for user_id in sub.subscribers
            )
        )
        for alert_id, sub in all_alerts.items()
    ]


@router.post("/alerts", response_model=AlertResponse)
async def create_alert(request: AlertRequest):
    """Создание нового алерта или подписка на существующий
    
    Args:
        request (AlertRequest): Запрос на создание алерта.

    Returns:
        AlertResponse: Созданный или существующий алерт.
        
    Raises:
        HTTPException: При ошибке парсинга выражения.
    """
    try:
        # Парсим выражение в AST
        expr = parse_expression(request.expression)
        
        # Создаем или подписываемся на существующий алерт
        listener = await CompositeListenerManager.instance().add_listener(
            expr, 
            int(request.user_id)
        )
        
        # Отправляем уведомление через WebSocket если пользователь подключен
        if WebSocketManager.instance().is_connected(int(request.user_id)):
            await WebSocketManager.instance().send_message(
                int(request.user_id),
                "alert_created",
                {
                    "alert_id": listener.id,
                    "expression": listener.readable_expression,
                    "message": "Алерт успешно создан"
                }
            )
        
        return AlertResponse(
            alert_id=listener.id,
            expression=listener.readable_expression,
            subscribers_count=len(listener.subscribers),
            is_websocket_connected=WebSocketManager.instance().is_connected(int(request.user_id))
        )
        
    except Exception as exc:
        raise HTTPException(
            status_code=400, 
            detail=f"Ошибка создания алерта: {str(exc)}"
        )


@router.delete("/alerts/{alert_id}")
async def delete_alert(alert_id: str, user_id: int):
    """Удаление алерта или отписка от него
    
    Args:
        alert_id (str): ID алерта.
        user_id (int): Telegram‑ID пользователя.

    Returns:
        dict: Результат операции.
    """
    success = await CompositeListenerManager.instance().unsubscribe_user(alert_id, user_id)
    
    if not success:
        raise HTTPException(
            status_code=404, 
            detail=f"Алерт {alert_id} не найден или пользователь не подписан"
        )
    
    # Отправляем уведомление через WebSocket если пользователь подключен
    if WebSocketManager.instance().is_connected(user_id):
        await WebSocketManager.instance().send_message(
            user_id,
            "alert_deleted",
            {
                "alert_id": alert_id,
                "message": "Вы отписаны от алерта"
            }
        )
    
    return {
        "success": True,
        "alert_id": alert_id,
        "message": "Успешно отписан от алерта"
    }
    

@router.delete("/alerts")
async def delete_all_alerts(user_id: int):
    """Удаление или отписка от всех алертов пользователя
    
    Args:
        user_id (int): Telegram‑ID пользователя.

    Returns:
        dict: Количество удаленных алертов.
    """
    removed_count = await CompositeListenerManager.instance().remove_user_from_all_listeners(user_id)
    
    # Отправляем уведомление через WebSocket если пользователь подключен
    if WebSocketManager.instance().is_connected(user_id):
        await WebSocketManager.instance().send_message(
            user_id,
            "all_alerts_deleted",
            {
                "removed_count": removed_count,
                "message": f"Отписаны от {removed_count} алертов"
            }
        )
    
    return {
        "success": True,
        "removed_count": removed_count,
        "message": f"Отписаны от {removed_count} алертов"
    }


@router.get("/alerts/{alert_id}")
async def get_alert_details(alert_id: str):
    """Получение детальной информации об алерте
    
    Args:
        alert_id (str): ID алерта.

    Returns:
        dict: Детальная информация об алерте.
    """
    listener = CompositeListenerManager.instance().get_listener_by_id(alert_id)
    
    if not listener:
        raise HTTPException(status_code=404, detail=f"Алерт {alert_id} не найден")
    
    # Проверяем сколько подписчиков подключено к WebSocket
    connected_subscribers = sum(
        1 for user_id in listener.subscribers 
        if WebSocketManager.instance().is_connected(user_id)
    )
    
    return {
        "alert_id": alert_id,
        "expression": listener.readable_expression,
        "subscribers": list(listener.subscribers),
        "subscribers_count": len(listener.subscribers),
        "connected_subscribers": connected_subscribers,
        "period_sec": listener.period_sec,
        "cooldown": getattr(listener, '_cooldown', 0),
        "last_matched": list(listener.matched_symbol_only) if hasattr(listener, 'matched_symbol_only') else []
    }


@router.post("/alerts/{alert_id}/subscribe")
async def subscribe_to_alert(alert_id: str, user_id: int):
    """Подписка на существующий алерт
    
    Args:
        alert_id (str): ID алерта.
        user_id (int): ID пользователя.

    Returns:
        dict: Результат подписки.
    """
    listener = CompositeListenerManager.instance().get_listener_by_id(alert_id)
    
    if not listener:
        raise HTTPException(status_code=404, detail=f"Алерт {alert_id} не найден")
    
    if user_id in listener.subscribers:
        return {
            "success": False,
            "message": "Вы уже подписаны на этот алерт"
        }
    
    listener.add_subscriber(user_id)
    
    # Отправляем уведомление через WebSocket если пользователь подключен
    if WebSocketManager.instance().is_connected(user_id):
        await WebSocketManager.instance().send_message(
            user_id,
            "subscribed_to_alert",
            {
                "alert_id": alert_id,
                "expression": listener.readable_expression,
                "message": "Подписка на алерт оформлена"
            }
        )
    
    return {
        "success": True,
        "alert_id": alert_id,
        "expression": listener.readable_expression,
        "message": "Успешно подписаны на алерт"
    }