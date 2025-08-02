from typing import List
from fastapi import FastAPI, HTTPException

from modules.composite.manager import CompositeListenerManager
from modules.composite.utils import ast_to_string
from .schemas import AlertRequest, AlertResponse

app = FastAPI()

@app.get("/alerts", response_model=List[AlertResponse])
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
            expression=sub.expression,
            readable_expression=sub.readable_expression,
        )
        for alert_id, sub in user_subscriptions.items()
    ]

@app.get("/alerts/all", response_model=List[AlertResponse])
async def get_all_alerts():
    """Получение всех алертов
    
    Returns:
        List[AlertResponse]: Список всех алертов.
    """
    return [
        AlertResponse(
            alert_id=alert_id,
            expression=sub.expression,
            readable_expression=sub.readable_expression,
        )
        for alert_id, sub in CompositeListenerManager.instance().all_alerts.items()
    ]


@app.post("/alerts", response_model=AlertResponse)
async def create_alert(request: AlertRequest):
    """Создание нового алерта или подписка на существующий
    
    Args:
        request (AlertRequest): Запрос на создание алерта.


    Returns:
        AlertResponse: Созданный алерт.
    """
    listener = await CompositeListenerManager.instance().add_listener(request.expression, request.user_id)
    return AlertResponse(
        alert_id=listener.id,
        expression=listener.expression,
        readable_expression=listener.readable_expression,
    )

@app.delete("/alerts/{alert_id}", response_model=AlertResponse)
async def delete_alert(alert_id: str, user_id: int):
    """Удаление алерта или отписка от него
    
    Args:
        alert_id (str): ID алерта.
        user_id (int): Telegram‑ID пользователя.

    Returns:
        bool: True если алерт был удален, False если не найден.
    """
    return await CompositeListenerManager.instance().unsubscribe_user(alert_id, user_id)
    
@app.delete("/alerts", response_model=List[AlertResponse])
async def delete_all_alerts(user_id: str):
    """Удаление или отписка от всех алертов пользователя
    
    Args:
        user_id (int): Telegram‑ID пользователя.

    Returns:
        int: Количество удаленных алертов.
    """
    return await CompositeListenerManager.instance().remove_user_from_all_listeners(user_id)

