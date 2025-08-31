import json
import datetime as dt
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import HTMLResponse
from config import logger

from modules.composite.manager import CompositeListenerManager
from .websocket_manager import WebSocketManager

router = APIRouter()

@router.websocket("/alerts/{user_id}")
async def websocket_alerts_endpoint(websocket: WebSocket, user_id: int) -> None:
    """WebSocket endpoint для получения алертов в реальном времени.
    
    Создает WebSocket соединение для пользователя и обрабатывает входящие сообщения.
    Отправляет приветственное сообщение, статистику пользователя и обрабатывает команды.
    
    Args:
        websocket: WebSocket соединение от клиента.
        user_id: Уникальный идентификатор пользователя.
        
    Raises:
        WebSocketDisconnect: При отключении клиента.
        Exception: При критических ошибках обработки.
        
    Note:
        - Отправляет приветственное сообщение при подключении
        - Отправляет статистику пользователя
        - Обрабатывает команды ping, get_status, get_my_alerts
        - Автоматически отключает пользователя при ошибках
    """
    await WebSocketManager.instance().connect(websocket, user_id)
    
    try:
        await websocket.send_text(json.dumps({
            "type": "connected",
            "message": "Подключен к системе алертов",
            "user_id": user_id,
            "timestamp": dt.datetime.utcnow().isoformat()
        }, ensure_ascii=False))
        
        user_subscriptions = CompositeListenerManager.instance().get_user_subscriptions(user_id)
        await websocket.send_text(json.dumps({
            "type": "user_stats",
            "alerts_count": len(user_subscriptions),
            "alert_ids": list(user_subscriptions.keys()),
            "timestamp": dt.datetime.utcnow().isoformat()
        }, ensure_ascii=False))
        
        while True:
            try:
                data = await websocket.receive_text()
                message = json.loads(data)
                await handle_websocket_command(websocket, user_id, message)
                    
            except json.JSONDecodeError:
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "message": "Неверный формат JSON",
                    "timestamp": dt.datetime.utcnow().isoformat()
                }, ensure_ascii=False))
            except WebSocketDisconnect:
                break
            except Exception as exc:
                logger.exception(f"[WS] Ошибка обработки сообщения от {user_id}: {exc}")
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "message": "Внутренняя ошибка сервера",
                    "timestamp": dt.datetime.utcnow().isoformat()
                }, ensure_ascii=False))
                
    except WebSocketDisconnect:
        logger.info(f"[WS] Пользователь {user_id} отключился")
    except Exception as exc:
        logger.exception(f"[WS] Критическая ошибка для пользователя {user_id}: {exc}")
    finally:
        await WebSocketManager.instance().disconnect(user_id)


async def handle_websocket_command(websocket: WebSocket, user_id: int, message: dict) -> None:
    """Обрабатывает команды WebSocket от клиента.
    
    Поддерживает следующие команды:
    - ping: Отвечает pong для проверки соединения
    - get_status: Возвращает статистику системы
    - get_my_alerts: Возвращает список алертов пользователя
    
    Args:
        websocket: WebSocket соединение для отправки ответов.
        user_id: Идентификатор пользователя.
        message: Словарь с командой и параметрами.
        
    Note:
        При неизвестной команде отправляет сообщение об ошибке.
    """
    command_type = message.get("type")
    
    if command_type == "ping":
        await websocket.send_text(json.dumps({
            "type": "pong",
            "timestamp": dt.datetime.utcnow().isoformat()
        }, ensure_ascii=False))
    
    elif command_type == "get_status":
        user_subs = CompositeListenerManager.instance().get_user_subscriptions(user_id)
        await websocket.send_text(json.dumps({
            "type": "status",
            "connected_users": len(WebSocketManager.instance().get_connected_users()),
            "your_alerts": len(user_subs),
            "total_alerts": len(CompositeListenerManager.instance().all_alerts),
            "timestamp": dt.datetime.utcnow().isoformat()
        }, ensure_ascii=False))
    
    elif command_type == "get_my_alerts":
        user_subs = CompositeListenerManager.instance().get_user_subscriptions(user_id)
        alerts_info = []
        for alert_id, listener in user_subs.items():
            alerts_info.append({
                "alert_id": alert_id,
                "expression": listener.readable_expression,
                "subscribers_count": len(listener.subscribers),
                "cooldown": listener._cooldown if hasattr(listener, '_cooldown') else 0
            })
        
        await websocket.send_text(json.dumps({
            "type": "my_alerts",
            "alerts": alerts_info,
            "timestamp": dt.datetime.utcnow().isoformat()
        }, ensure_ascii=False))
    
    else:
        await websocket.send_text(json.dumps({
            "type": "error",
            "message": f"Неизвестная команда: {command_type}",
            "timestamp": dt.datetime.utcnow().isoformat()
        }, ensure_ascii=False))


@router.get("/ws/status")
async def get_websocket_status() -> dict:
    """Получает статистику WebSocket соединений и алертов.
    
    Возвращает общую статистику системы, включая количество
    подключенных пользователей, общее количество алертов и подписчиков.
    
    Returns:
        dict: Словарь со статистикой системы:
            - websocket: Статистика WebSocket соединений
            - alerts: Статистика алертов (общее количество и подписчиков)
            - timestamp: Временная метка запроса
            
    Example:
        response = await get_websocket_status()
        print(response['websocket']['connected_users'])
        5
    """
    ws_stats = WebSocketManager.instance().get_stats()
    manager = CompositeListenerManager.instance()
    
    return {
        "websocket": ws_stats,
        "alerts": {
            "total_alerts": len(manager.all_alerts),
            "total_subscribers": sum(
                len(listener.subscribers) 
                for listener in manager.all_alerts.values()
            )
        },
        "timestamp": dt.datetime.utcnow().isoformat()
    }


@router.post("/ws/test-alert/{user_id}")
async def send_test_alert(user_id: int, message: str = "Тестовый алерт") -> dict:
    """Отправляет тестовый алерт указанному пользователю.
    
    Проверяет подключение пользователя и отправляет тестовое уведомление
    для проверки работы WebSocket соединения.
    
    Args:
        user_id: Идентификатор пользователя для отправки алерта.
        message: Текст тестового сообщения. По умолчанию "Тестовый алерт".
        
    Returns:
        dict: Результат отправки:
            - sent: True если алерт отправлен успешно
            - user_id: ID пользователя
            - message: Отправленное сообщение
            
    Raises:
        HTTPException: Если пользователь не подключен (404).
        
    Example:
        >>> result = await send_test_alert(12345, "Тест")
        >>> print(result['sent'])
        True
    """
    if not WebSocketManager.instance().is_connected(user_id):
        raise HTTPException(status_code=404, detail=f"Пользователь {user_id} не подключен")
    
    test_data = {
        "type": "alert",
        "alert_id": "test-alert",
        "tickers": ["TESTUSDT"],
        "readable_expression": "Тестовое условие",
        "message": message,
        "timestamp": dt.datetime.utcnow().isoformat(),
        "cooldown": 0
    }
    
    success = await WebSocketManager.instance().send_alert(user_id, test_data)
    return {
        "sent": success,
        "user_id": user_id,
        "message": message
    }


@router.post("/ws/broadcast-message")
async def broadcast_message(message: str, message_type: str = "announcement") -> dict:
    """Отправляет сообщение всем подключенным пользователям.
    
    Создает широковещательное сообщение и отправляет его всем
    активным WebSocket соединениям.
    
    Args:
        message: Текст сообщения для отправки.
        message_type: Тип сообщения (announcement, warning, info). 
                     По умолчанию "announcement".
                     
    Returns:
        dict: Статистика отправки:
            - sent_to: Количество пользователей, получивших сообщение
            - total_connected: Общее количество подключенных пользователей
            - message: Отправленное сообщение
            - type: Тип сообщения
            
    Example:
        result = await broadcast_message("Обновление системы", "info")
        print(f"Отправлено {result['sent_to']} пользователям")
        Отправлено 15 пользователям
    """
    connected_users = WebSocketManager.instance().get_connected_users()
    
    broadcast_data = {
        "type": message_type,
        "message": message,
        "timestamp": dt.datetime.utcnow().isoformat()
    }
    
    sent_count = await WebSocketManager.instance().broadcast_alert(connected_users, broadcast_data)
    
    return {
        "sent_to": sent_count,
        "total_connected": len(connected_users),
        "message": message,
        "type": message_type
    }



@router.get("/demo")
async def get_demo_page() -> HTMLResponse:
    """Возвращает HTML страницу для демонстрации WebSocket функциональности.
    
    Создает интерактивную веб-страницу с возможностью:
    - Подключения к WebSocket
    - Создания и управления алертами
    - Просмотра входящих сообщений в реальном времени
    - Тестирования различных WebSocket команд
    - Просмотра справочника синтаксиса (интегрированный модал)
    
    Returns:
        HTMLResponse: HTML страница с JavaScript кодом для демонстрации
            WebSocket функциональности системы алертов и встроенным справочником.
            
    Note:
        Страница содержит полный интерфейс для тестирования всех
        возможностей WebSocket API, включая создание алертов,
        получение уведомлений, управление соединением и справочник синтаксиса.
    """
    html = """
<!DOCTYPE html>
<html>
<head>
    <title>🚨 Alerts Dashboard</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body { 
            font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            color: #333;
        }
        
        .container {
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
            display: grid;
            grid-template-columns: 350px 1fr;
            gap: 20px;
            min-height: 100vh;
        }
        
        .sidebar {
            background: rgba(255, 255, 255, 0.95);
            backdrop-filter: blur(10px);
            border-radius: 15px;
            padding: 20px;
            height: fit-content;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
        }
        
        .main-content {
            display: flex;
            flex-direction: column;
            gap: 20px;
        }
        
        .header {
            background: rgba(255, 255, 255, 0.95);
            backdrop-filter: blur(10px);
            border-radius: 15px;
            padding: 20px;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        
        .header-controls {
            display: flex;
            gap: 10px;
            align-items: center;
        }
        
        .help-btn {
            background: linear-gradient(135deg, #17a2b8, #138496);
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 20px;
            cursor: pointer;
            font-size: 14px;
            font-weight: 600;
            transition: all 0.3s ease;
            display: flex;
            align-items: center;
            gap: 5px;
        }
        
        .help-btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 15px rgba(23, 162, 184, 0.4);
        }
        
        .status-indicator {
            padding: 8px 16px;
            border-radius: 20px;
            color: white;
            font-weight: 600;
            font-size: 14px;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        
        .status-indicator::before {
            content: '';
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: currentColor;
            animation: pulse 2s infinite;
        }
        
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }
        
        .connected { 
            background: linear-gradient(135deg, #4CAF50, #45a049);
        }
        
        .disconnected { 
            background: linear-gradient(135deg, #f44336, #d32f2f);
        }
        
        .section {
            background: rgba(255, 255, 255, 0.95);
            backdrop-filter: blur(10px);
            border-radius: 15px;
            padding: 20px;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
        }
        
        .section h3 {
            margin-bottom: 15px;
            color: #2c3e50;
            font-size: 18px;
            font-weight: 600;
        }
        
        .form-group {
            margin-bottom: 15px;
        }
        
        .form-group label {
            display: block;
            margin-bottom: 5px;
            font-weight: 600;
            color: #555;
        }
        
        input, button {
            padding: 12px 16px;
            border: 2px solid #e0e0e0;
            border-radius: 8px;
            font-size: 14px;
            transition: all 0.3s ease;
        }
        
        input {
            width: 100%;
            background: white;
        }
        
        input:focus {
            outline: none;
            border-color: #667eea;
            box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
        }
        
        button {
            cursor: pointer;
            border: none;
            color: white;
            font-weight: 600;
            background: linear-gradient(135deg, #667eea, #764ba2);
            width: 100%;
            margin-top: 5px;
        }
        
        button:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 15px rgba(102, 126, 234, 0.4);
        }
        
        .btn-danger {
            background: linear-gradient(135deg, #f44336, #d32f2f);
        }
        
        .btn-danger:hover {
            box-shadow: 0 4px 15px rgba(244, 67, 54, 0.4);
        }
        
        .btn-success {
            background: linear-gradient(135deg, #4CAF50, #45a049);
        }
        
        .btn-success:hover {
            box-shadow: 0 4px 15px rgba(76, 175, 80, 0.4);
        }
        
        .btn-secondary {
            background: linear-gradient(135deg, #6c757d, #5a6268);
        }
        
        .btn-secondary:hover {
            box-shadow: 0 4px 15px rgba(108, 117, 125, 0.4);
        }
        
        .btn-small {
            padding: 6px 12px;
            font-size: 12px;
            margin: 2px;
            width: auto;
        }
        
        /* Modal Styles */
        .modal {
            display: none;
            position: fixed;
            z-index: 1000;
            left: 0;
            top: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.8);
            backdrop-filter: blur(5px);
        }
        
        .modal-content {
            background: white;
            margin: 2% auto;
            padding: 0;
            border-radius: 20px;
            width: 95%;
            max-width: 1200px;
            max-height: 90vh;
            overflow-y: auto;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
            animation: modalSlideIn 0.3s ease-out;
        }
        
        @keyframes modalSlideIn {
            from {
                transform: translateY(-50px) scale(0.9);
                opacity: 0;
            }
            to {
                transform: translateY(0) scale(1);
                opacity: 1;
            }
        }
        
        .modal-header {
            background: linear-gradient(135deg, #667eea, #764ba2);
            color: white;
            padding: 20px 30px;
            border-radius: 20px 20px 0 0;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        
        .modal-header h2 {
            margin: 0;
            font-size: 1.8em;
        }
        
        .close-btn {
            background: none;
            border: none;
            color: white;
            font-size: 2em;
            cursor: pointer;
            width: auto;
            margin: 0;
            padding: 0;
            line-height: 1;
        }
        
        .close-btn:hover {
            opacity: 0.7;
            transform: none;
            box-shadow: none;
        }
        
        .modal-body {
            padding: 30px;
        }
        
        .syntax-section {
            margin-bottom: 40px;
        }

        .section-title {
            font-size: 1.8em;
            color: #2c3e50;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 3px solid #667eea;
            font-weight: 600;
        }

        .modules-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(500px, 1fr));
            gap: 25px;
            margin-bottom: 30px;
        }

        .module-card {
            background: linear-gradient(135deg, #f8f9fa, #e9ecef);
            border-radius: 15px;
            padding: 25px;
            box-shadow: 0 8px 25px rgba(0, 0, 0, 0.1);
            border-left: 5px solid #667eea;
            transition: all 0.3s ease;
        }

        .module-card:hover {
            transform: translateY(-5px);
            box-shadow: 0 15px 35px rgba(0, 0, 0, 0.15);
        }

        .module-header-help {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 15px;
        }

        .module-name {
            font-size: 1.4em;
            font-weight: 700;
            color: #2c3e50;
            background: linear-gradient(135deg, #667eea, #764ba2);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }

        .module-type {
            background: linear-gradient(135deg, #4CAF50, #45a049);
            color: white;
            padding: 5px 12px;
            border-radius: 20px;
            font-size: 0.8em;
            font-weight: 600;
        }

        .module-description {
            color: #555;
            margin-bottom: 20px;
            line-height: 1.6;
        }

        .syntax-box {
            background: #2c3e50;
            color: #ecf0f1;
            padding: 15px;
            border-radius: 8px;
            font-family: 'SF Mono', Monaco, monospace;
            margin: 15px 0;
            position: relative;
            overflow-x: auto;
        }

        .syntax-title {
            color: #3498db;
            font-weight: 600;
            margin-bottom: 8px;
        }

        .param-table {
            width: 100%;
            border-collapse: collapse;
            margin: 15px 0;
            background: white;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 4px 15px rgba(0, 0, 0, 0.1);
        }

        .param-table th,
        .param-table td {
            padding: 12px 15px;
            text-align: left;
            border-bottom: 1px solid #e0e0e0;
        }

        .param-table th {
            background: linear-gradient(135deg, #667eea, #764ba2);
            color: white;
            font-weight: 600;
            font-size: 0.9em;
        }

        .param-table tr:hover {
            background: #f8f9fa;
        }

        .param-name {
            font-weight: 600;
            color: #e74c3c;
            font-family: monospace;
        }

        .param-type {
            color: #3498db;
            font-style: italic;
        }

        .operators-section {
            background: linear-gradient(135deg, #fff3cd, #ffeaa7);
            border-radius: 15px;
            padding: 25px;
            margin-bottom: 30px;
            border-left: 5px solid #ffc107;
        }

        .operators-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
        }

        .operator-card {
            background: white;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 4px 15px rgba(0, 0, 0, 0.1);
        }

        .operator-symbol {
            font-size: 2em;
            font-weight: bold;
            color: #e74c3c;
            margin-bottom: 10px;
        }

        .examples-section {
            background: linear-gradient(135deg, #e8f5e8, #d4edda);
            border-radius: 15px;
            padding: 25px;
            border-left: 5px solid #28a745;
        }

        .example-box {
            background: #2c3e50;
            color: #ecf0f1;
            border-radius: 8px;
            margin: 10px 0;
            font-family: monospace;
            position: relative;
            overflow: hidden;
        }

        .example-content {
            padding: 15px;
        }

        .example-comment {
            color: #95a5a6;
            font-style: italic;
        }

        .copy-btn-modal {
            background: #3498db;
            color: white;
            border: none;
            padding: 8px 15px;
            border-radius: 0 0 8px 8px;
            cursor: pointer;
            font-size: 0.75em;
            opacity: 0.9;
            transition: opacity 0.3s;
            width: 100%;
            border-top: 1px solid rgba(255,255,255,0.1);
        }

        .copy-btn-modal:hover {
            opacity: 1;
        }

        .warning-box {
            background: linear-gradient(135deg, #ffe6e6, #ffcccc);
            border-left: 5px solid #dc3545;
            padding: 15px;
            border-radius: 8px;
            margin: 15px 0;
        }

        .info-box {
            background: linear-gradient(135deg, #e3f2fd, #bbdefb);
            border-left: 5px solid #2196F3;
            padding: 15px;
            border-radius: 8px;
            margin: 15px 0;
        }

        .highlight {
            background: #fff3cd;
            padding: 2px 6px;
            border-radius: 4px;
            font-weight: 600;
        }
        
        /* Existing styles for alerts dashboard */
        .alerts-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(400px, 1fr));
            gap: 20px;
            max-height: 70vh;
            overflow-y: auto;
            padding-right: 10px;
        }
        
        .alert-card {
            background: white;
            border-radius: 12px;
            padding: 20px;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.1);
            border-left: 4px solid #667eea;
            transition: all 0.3s ease;
            position: relative;
            overflow: hidden;
        }
        
        .alert-card:hover {
            transform: translateY(-5px);
            box-shadow: 0 8px 30px rgba(0, 0, 0, 0.15);
        }
        
        .alert-card.triggered {
            animation: alertTrigger 3s ease-in-out;
            border-left-color: #ff4444;
        }
        
        @keyframes alertTrigger {
            0% { transform: scale(1); }
            10% { transform: scale(1.05); box-shadow: 0 0 30px rgba(255, 68, 68, 0.6); }
            20% { transform: scale(1); }
            30% { transform: scale(1.05); box-shadow: 0 0 30px rgba(255, 68, 68, 0.6); }
            100% { transform: scale(1); }
        }
        
        .alert-header {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            margin-bottom: 15px;
        }
        
        .alert-id {
            font-family: 'Courier New', monospace;
            font-size: 12px;
            color: #666;
            background: #f5f5f5;
            padding: 4px 8px;
            border-radius: 4px;
        }
        
        .alert-expression {
            font-family: 'Courier New', monospace;
            background: linear-gradient(135deg, #f8f9fa, #e9ecef);
            padding: 12px;
            border-radius: 8px;
            font-size: 14px;
            color: #2c3e50;
            margin: 10px 0;
            border: 1px solid #dee2e6;
        }
        
        .alert-stats {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin: 10px 0;
            font-size: 12px;
            color: #666;
        }
        
        .alert-actions {
            display: flex;
            gap: 8px;
            margin-top: 15px;
        }
        
        .alert-actions button {
            flex: 1;
            padding: 8px 12px;
            font-size: 12px;
            margin: 0;
        }
        
        .blacklist-section {
            margin-top: 15px;
            padding-top: 15px;
            border-top: 1px solid #eee;
        }
        
        .blacklist-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 10px;
        }
        
        .blacklist-title {
            font-size: 13px;
            font-weight: 600;
            color: #555;
        }
        
        .blacklist-count {
            font-size: 11px;
            color: #999;
            background: #f8f9fa;
            padding: 2px 6px;
            border-radius: 8px;
        }
        
        .blacklist-tags {
            display: flex;
            flex-wrap: wrap;
            gap: 5px;
            margin-bottom: 10px;
            min-height: 20px;
        }
        
        .blacklist-tag {
            background: linear-gradient(135deg, #dc3545, #c82333);
            color: white;
            padding: 3px 8px;
            border-radius: 12px;
            font-size: 11px;
            font-weight: 500;
            display: flex;
            align-items: center;
            gap: 4px;
        }
        
        .blacklist-tag .remove-btn {
            cursor: pointer;
            font-weight: bold;
            opacity: 0.7;
        }
        
        .blacklist-tag .remove-btn:hover {
            opacity: 1;
        }
        
        .blacklist-input-row {
            display: flex;
            gap: 5px;
        }
        
        .blacklist-input {
            flex: 1;
            padding: 6px 8px;
            font-size: 12px;
            border: 1px solid #ddd;
            border-radius: 4px;
            text-transform: uppercase;
        }
        
        .add-blacklist-btn {
            padding: 6px 12px;
            font-size: 12px;
            background: #6c757d;
            border: none;
            color: white;
            border-radius: 4px;
            cursor: pointer;
            width: auto;
            margin: 0;
        }
        
        .add-blacklist-btn:hover {
            background: #5a6268;
            transform: none;
            box-shadow: none;
        }
        
        .triggered-alert {
            background: white;
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 15px;
            border-left: 4px solid #ff4444;
            box-shadow: 0 4px 20px rgba(255, 68, 68, 0.2);
            animation: newAlert 0.5s ease-out;
        }
        
        .triggered-alert.filtered {
            background: linear-gradient(135deg, #fff3cd, #ffeaa7);
            border-left-color: #ffc107;
        }
        
        @keyframes newAlert {
            0% { 
                opacity: 0; 
                transform: translateX(100%) scale(0.8); 
            }
            100% { 
                opacity: 1; 
                transform: translateX(0) scale(1); 
            }
        }
        
        .triggered-header {
            display: flex;
            align-items: center;
            gap: 10px;
            margin-bottom: 10px;
        }
        
        .triggered-time {
            font-size: 12px;
            color: #666;
        }
        
        .triggered-tickers {
            display: flex;
            flex-wrap: wrap;
            gap: 5px;
            margin: 10px 0;
        }
        
        .ticker-badge {
            background: linear-gradient(135deg, #ff4444, #cc0000);
            color: white;
            padding: 4px 8px;
            border-radius: 12px;
            font-size: 11px;
            font-weight: 600;
        }
        
        .ticker-badge.filtered {
            background: linear-gradient(135deg, #ffc107, #e0a800);
            color: #000;
        }
        
        .filtered-info {
            font-size: 11px;
            color: #856404;
            background: rgba(255, 193, 7, 0.1);
            padding: 5px 8px;
            border-radius: 4px;
            margin-top: 8px;
        }
        
        .examples {
            background: linear-gradient(135deg, #e3f2fd, #bbdefb);
            padding: 15px;
            border-radius: 8px;
            margin: 15px 0;
            font-size: 13px;
            line-height: 1.4;
        }
        
        .examples code {
            background: rgba(255, 255, 255, 0.8);
            padding: 2px 6px;
            border-radius: 3px;
            font-family: 'Courier New', monospace;
        }
        
        .my-alerts-list {
            max-height: 300px;
            overflow-y: auto;
        }
        
        .triggered-alerts {
            max-height: 400px;
            overflow-y: auto;
            padding-right: 10px;
        }
        
        .no-alerts {
            text-align: center;
            color: #666;
            padding: 40px 20px;
            font-style: italic;
        }
        
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 15px;
            margin-bottom: 20px;
        }
        
        .stat-card {
            background: white;
            padding: 15px;
            border-radius: 8px;
            text-align: center;
            box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);
        }
        
        .stat-value {
            font-size: 24px;
            font-weight: bold;
            color: #667eea;
        }
        
        .stat-label {
            font-size: 12px;
            color: #666;
            margin-top: 5px;
        }
        
        .ws-commands {
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
        }
        
        .ws-commands button {
            flex: 1;
            min-width: 80px;
            font-size: 12px;
            padding: 8px 12px;
        }
        
        @media (max-width: 768px) {
            .container {
                grid-template-columns: 1fr;
                padding: 10px;
            }
            
            .header {
                flex-direction: column;
                gap: 10px;
                text-align: center;
            }
            
            .alerts-grid {
                grid-template-columns: 1fr;
            }
            
            .modules-grid {
                grid-template-columns: 1fr;
            }
            
            .operators-grid {
                grid-template-columns: 1fr;
            }
            
            .modal-content {
                width: 98%;
                margin: 1% auto;
            }
            
            .modal-body {
                padding: 15px;
            }
        }
    </style>
</head>
<body>
    <!-- Help Modal -->
    <div id="helpModal" class="modal">
        <div class="modal-content">
            <div class="modal-header">
                <h2>📚 Справочник синтаксиса алертов</h2>
                <button class="close-btn" onclick="closeHelpModal()">&times;</button>
            </div>
            <div class="modal-body">
                <!-- Операторы и логика -->
                <div class="syntax-section">
                    <h2 class="section-title">🔧 Операторы и логические связки</h2>
                    
                    <div class="operators-section">
                        <div class="operators-grid">
                            <div class="operator-card">
                                <div class="operator-symbol">&</div>
                                <h4>Логическое И (AND)</h4>
                                <p>Все условия должны выполняться одновременно</p>
                                <div class="syntax-box">price > 5 300 60 & volume > 1000000 60</div>
                            </div>
                            
                            <div class="operator-card">
                                <div class="operator-symbol">|</div>
                                <h4>Логическое ИЛИ (OR)</h4>
                                <p>Хотя бы одно из условий должно выполниться</p>
                                <div class="syntax-box">price > 5 300 60 | oi > 10</div>
                            </div>
                            
                            <div class="operator-card">
                                <div class="operator-symbol">@</div>
                                <h4>Cooldown (задержка)</h4>
                                <p>Ограничивает частоту срабатываний алерта</p>
                                <div class="syntax-box">price > 5 300 60 @120</div>
                                <small>Алерт сработает не чаще раза в 120 секунд</small>
                                <small>Ставится строго в конце выражения</small>
                            </div>
                        </div>

                        <div class="info-box">
                            <strong>Приоритет операций:</strong> сначала <code>&</code> (AND), затем <code>|</code> (OR). 
                            Используйте скобки для изменения приоритета: <code>(A | B) & C</code>
                        </div>
                    </div>
                </div>

                <!-- Модули -->
                <div class="syntax-section">
                    <h2 class="section-title">📊 Доступные модули</h2>
                    
                    <div class="modules-grid">
                        <!-- Price Module -->
                        <div class="module-card">
                            <div class="module-header-help">
                                <span class="module-name">price</span>
                                <span class="module-type">Цена</span>
                            </div>
                            <div class="module-description">
                                Отслеживает изменение цены за указанный временной интервал
                            </div>
                            
                            <div class="syntax-box">
                                <div class="syntax-title">Синтаксис:</div>
                                price &lt;оператор&gt; &lt;процент&gt; &lt;окно&gt; [период_проверки]
                            </div>
                            
                            <table class="param-table">
                                <tr>
                                    <th>Параметр</th>
                                    <th>Тип</th>
                                    <th>Описание</th>
                                </tr>
                                <tr>
                                    <td class="param-name">процент</td>
                                    <td class="param-type">float</td>
                                    <td>Порог изменения цены в %</td>
                                </tr>
                                <tr>
                                    <td class="param-name">окно</td>
                                    <td class="param-type">int</td>
                                    <td>Период расчета в секундах</td>
                                </tr>
                                <tr>
                                    <td class="param-name">период</td>
                                    <td class="param-type">int</td>
                                    <td>Частота проверки (опционально)</td>
                                </tr>
                            </table>
                            
                            <div class="example-box">
                                <div class="example-content">
                                    <div>price > 5 300 60 <span class="example-comment">// +/-5% за 5 минут, проверка каждую минуту</span></div>
                                </div>
                                <button class="copy-btn-modal" onclick="copyToClipboardModal('price > 5 300 60')">Copy</button>
                            </div>
                        </div>

                        <!-- Volume Module -->
                        <div class="module-card">
                            <div class="module-header-help">
                                <span class="module-name">volume</span>
                                <span class="module-type">Объем</span>
                            </div>
                            <div class="module-description">
                                Отслеживает абсолютный объем торгов в USD за временное окно
                            </div>
                            
                            <div class="syntax-box">
                                <div class="syntax-title">Синтаксис:</div>
                                volume &lt;оператор&gt; &lt;сумма_USD&gt; &lt;окно&gt; [период]
                            </div>
                            
                            <table class="param-table">
                                <tr>
                                    <th>Параметр</th>
                                    <th>Тип</th>
                                    <th>Описание</th>
                                </tr>
                                <tr>
                                    <td class="param-name">сумма_USD</td>
                                    <td class="param-type">float</td>
                                    <td>Пороговый объем в долларах</td>
                                </tr>
                                <tr>
                                    <td class="param-name">окно</td>
                                    <td class="param-type">int</td>
                                    <td>Период расчета в секундах</td>
                                </tr>
                            </table>
                            
                            <div class="example-box">
                                <div class="example-content">
                                    <div>volume > 1000000 300 60 <span class="example-comment">// >1M USD за 5 минут, проверка каждую минуту</span></div>
                                </div>
                                <button class="copy-btn-modal" onclick="copyToClipboardModal('volume > 1000000 300 60')">Copy</button>
                            </div>
                        </div>

                        <!-- Volume Change Module -->
                        <div class="module-card">
                            <div class="module-header-help">
                                <span class="module-name">volume_change</span>
                                <span class="module-type">Изм. объема</span>
                            </div>
                            <div class="module-description">
                                Сравнивает объем торгов между двумя соседними временными окнами
                            </div>
                            
                            <div class="syntax-box">
                                <div class="syntax-title">Синтаксис:</div>
                                volume_change &lt;оператор&gt; &lt;процент&gt; &lt;окно&gt; [период]
                            </div>
                            
                            <table class="param-table">
                                <tr>
                                    <th>Параметр</th>
                                    <th>Тип</th>
                                    <th>Описание</th>
                                </tr>
                                <tr>
                                    <td class="param-name">процент</td>
                                    <td class="param-type">float</td>
                                    <td>Порог изменения объема в %</td>
                                </tr>
                                <tr>
                                    <td class="param-name">окно</td>
                                    <td class="param-type">int</td>
                                    <td>Размер окна сравнения в секундах</td>
                                </tr>
                            </table>
                            
                            <div class="example-box">
                                <div class="example-content">
                                    <div>volume_change > 100 1800 60 <span class="example-comment">// +100% за 30 минут</span></div>
                                </div>
                                <button class="copy-btn-modal" onclick="copyToClipboardModal('volume_change > 100 1800 60')">Copy</button>
                            </div>
                        </div>

                        <!-- OI Module -->
                        <div class="module-card">
                            <div class="module-header-help">
                                <span class="module-name">oi</span>
                                <span class="module-type">Откр. интерес</span>
                            </div>
                            <div class="module-description">
                                Отслеживает изменение открытого интереса относительно медианы за 24 часа
                            </div>
                            
                            <div class="syntax-box">
                                <div class="syntax-title">Синтаксис:</div>
                                oi &lt;оператор&gt; &lt;процент&gt;
                            </div>
                            
                            <table class="param-table">
                                <tr>
                                    <th>Параметр</th>
                                    <th>Тип</th>
                                    <th>Описание</th>
                                </tr>
                                <tr>
                                    <td class="param-name">процент</td>
                                    <td class="param-type">float</td>
                                    <td>Отклонение от медианы в %</td>
                                </tr>
                            </table>
                            
                            <div class="example-box">
                                <div class="example-content">
                                    <div>oi > 200 <span class="example-comment">// OI вырос на 200% от медианы</span></div>
                                </div>
                                <button class="copy-btn-modal" onclick="copyToClipboardModal('oi > 200')">Copy</button>
                            </div>
                        </div>

                        <!-- OI Sum Module -->
                        <div class="module-card">
                            <div class="module-header-help">
                                <span class="module-name">oi_sum</span>
                                <span class="module-type">Абс. OI</span>
                            </div>
                            <div class="module-description">
                                Проверяет абсолютное значение открытого интереса в USD
                            </div>
                            
                            <div class="syntax-box">
                                <div class="syntax-title">Синтаксис:</div>
                                oi_sum &lt;оператор&gt; &lt;сумма_USD&gt;
                            </div>
                            
                            <table class="param-table">
                                <tr>
                                    <th>Параметр</th>
                                    <th>Тип</th>
                                    <th>Описание</th>
                                </tr>
                                <tr>
                                    <td class="param-name">сумма_USD</td>
                                    <td class="param-type">float</td>
                                    <td>Пороговое значение OI в долларах</td>
                                </tr>
                            </table>
                            
                            <div class="example-box">
                                <div class="example-content">
                                    <div>oi_sum > 3000000000 <span class="example-comment">// OI больше 3 MЛРД USD</span></div>
                                </div>
                                <button class="copy-btn-modal" onclick="copyToClipboardModal('oi_sum > 3000000000')">Copy</button>
                            </div>
                        </div>

                        <!-- Funding Module -->
                        <div class="module-card">
                            <div class="module-header-help">
                                <span class="module-name">funding</span>
                                <span class="module-type">Фандинг</span>
                            </div>
                            <div class="module-description">
                                Отслеживает фандинг ставки перед расчетом
                            </div>
                            
                            <div class="syntax-box">
                                <div class="syntax-title">Синтаксис:</div>
                                funding &lt;оператор&gt; &lt;процент&gt; &lt;время_до_расчета&gt;
                            </div>
                            
                            <table class="param-table">
                                <tr>
                                    <th>Параметр</th>
                                    <th>Тип</th>
                                    <th>Описание</th>
                                </tr>
                                <tr>
                                    <td class="param-name">процент</td>
                                    <td class="param-type">float</td>
                                    <td>Абсолютное значение ставки в %</td>
                                </tr>
                                <tr>
                                    <td class="param-name">время</td>
                                    <td class="param-type">int</td>
                                    <td>Макс. время до расчета в секундах</td>
                                </tr>
                            </table>
                            
                            <div class="example-box">
                                <div class="example-content">
                                    <div>funding > 1 3600 <span class="example-comment">// |funding| >= 1% за час до расчета</span></div>
                                </div>
                                <button class="copy-btn-modal" onclick="copyToClipboardModal('funding > 1 3600')">Copy</button>
                            </div>
                        </div>

                        <!-- Order Module -->
                        <div class="module-card">
                            <div class="module-header-help">
                                <span class="module-name">order</span>
                                <span class="module-type">Ордера</span>
                            </div>
                            <div class="module-description">
                                Отслеживает крупные ордера в стакане, которые держатся определенное время
                            </div>
                            
                            <div class="syntax-box">
                                <div class="syntax-title">Синтаксис:</div>
                                order &lt;оператор&gt; &lt;размер_USD&gt; &lt;макс_%_откл&gt; &lt;мин_длительность&gt;
                            </div>
                            
                            <table class="param-table">
                                <tr>
                                    <th>Параметр</th>
                                    <th>Тип</th>
                                    <th>Описание</th>
                                </tr>
                                <tr>
                                    <td class="param-name">размер_USD</td>
                                    <td class="param-type">float</td>
                                    <td>Минимальный размер ордера в USD(от 200 000 USD)</td>
                                </tr>
                                <tr>
                                    <td class="param-name">макс_%</td>
                                    <td class="param-type">float</td>
                                    <td>Максимальное отклонение от цены в % (от 0 до 10%)</td>
                                </tr>
                                <tr>
                                    <td class="param-name">длительность</td>
                                    <td class="param-type">int</td>
                                    <td>Минимальное время жизни в секундах</td>
                                </tr>
                            </table>
                            
                            <div class="example-box">
                                <div class="example-content">
                                    <div>order > 1000000 5 300 <span class="example-comment">// Ордер >1M USD, ±5% от цены, >5 минут</span></div>
                                </div>
                                <button class="copy-btn-modal" onclick="copyToClipboardModal('order > 1000000 5 300')">Copy</button>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- Операторы сравнения -->
                <div class="syntax-section">
                    <h2 class="section-title">⚖️ Операторы сравнения</h2>
                    
                    <div class="operators-section">
                        <table class="param-table">
                            <tr>
                                <th>Оператор</th>
                                <th>Описание</th>
                                <th>Пример использования</th>
                            </tr>
                            <tr>
                                <td class="param-name">></td>
                                <td>Больше порогового значения</td>
                                <td><code>price > 5 300</code></td>
                            </tr>
                            <tr>
                                <td class="param-name"><</td>
                                <td>Меньше порогового значения</td>
                                <td><code>volume_change < 100 600</code></td>
                            </tr>
                        </table>
                    </div>
                </div>

                <!-- Примеры -->
                <div class="syntax-section">
                    <h2 class="section-title">💡 Практические примеры</h2>
                    
                    <div class="examples-section">
                        <h3>Простые условия:</h3>
                        
                        <div class="example-box">
                            <div class="example-content">
                                <div>price > 3 300 60 <span class="example-comment">// Цена изменилась на ±3% за 5 минут</span></div>
                            </div>
                            <button class="copy-btn-modal" onclick="copyToClipboardModal('price > 3 300 60')">Copy</button>
                        </div>
                        
                        <div class="example-box">
                            <div class="example-content">
                                <div>volume > 5000000 600 <span class="example-comment">// Объем >5M USD за 10 минут</span></div>
                            </div>
                            <button class="copy-btn-modal" onclick="copyToClipboardModal('volume > 5000000 600')">Copy</button>
                        </div>
                        
                        <div class="example-box">
                            <div class="example-content">
                                <div>oi > 250 <span class="example-comment">// OI вырос на 250% от медианы</span></div>
                            </div>
                            <button class="copy-btn-modal" onclick="copyToClipboardModal('oi > 250')">Copy</button>
                        </div>

                        <h3>Сложные условия с логикой:</h3>
                        
                        <div class="example-box">
                            <div class="example-content">
                                <div>price > 2 180 60 & volume > 2000000 180 <span class="example-comment">// Цена И объем одновременно</span></div>
                            </div>
                            <button class="copy-btn-modal" onclick="copyToClipboardModal('price > 2 180 60 & volume > 2000000 180')">Copy</button>
                        </div>
                        
                        <div class="example-box">
                            <div class="example-content">
                                <div>oi > 100 | funding > 1.5 1800 <span class="example-comment">// OI ИЛИ высокий фандинг</span></div>
                            </div>
                            <button class="copy-btn-modal" onclick="copyToClipboardModal('oi > 100 | funding > 1.5 1800')">Copy</button>
                        </div>
                        
                        <div class="example-box">
                            <div class="example-content">
                                <div>(price > 5 300 & volume > 1000000 300) | oi > 300 <span class="example-comment">// Группировка со скобками</span></div>
                            </div>
                            <button class="copy-btn-modal" onclick="copyToClipboardModal('(price > 5 300 & volume > 1000000 300) | oi > 300')">Copy</button>
                        </div>

                        <h3>С задержкой (cooldown):</h3>
                        
                        <div class="example-box">
                            <div class="example-content">
                                <div>price > 10 60 @300 <span class="example-comment">// Сильное движение цены, не чаще раза в 5 минут</span></div>
                            </div>
                            <button class="copy-btn-modal" onclick="copyToClipboardModal('price > 10 60 @300')">Copy</button>
                        </div>
                        
                        <div class="example-box">
                            <div class="example-content">
                                <div>volume_change > 500 900 60 @600 <span class="example-comment">// Взрывной рост объема, cooldown 10 минут</span></div>
                            </div>
                            <button class="copy-btn-modal" onclick="copyToClipboardModal('volume_change > 500 900 60 @600')">Copy</button>
                        </div>
                    </div>
                </div>

                <!-- Важные заметки -->
                <div class="syntax-section">
                    <h2 class="section-title">⚠️ Важные заметки</h2>
                    
                    <div class="warning-box">
                        <strong>Внимание:</strong>
                        <ul style="margin-left: 20px; margin-top: 10px;">
                            <li>Модуль <code>funding</code> работает с абсолютным значением ставки (|rate|)</li>
                            <li>Cooldown применяется к результирующему выражению и работает по каждому тикеру отдельно</li>
                        </ul>
                    </div>
                    
                </div>
            </div>
        </div>
    </div>

    <div class="container">
        <!-- Sidebar -->
        <div class="sidebar">
            <!-- Connection -->
            <div class="section">
                <h3>🔌 Подключение</h3>
                <div class="form-group">
                    <label>User ID:</label>
                    <input type="number" id="userId" value="12345" />
                </div>
                <button onclick="connect()" class="btn-success">Подключить</button>
                <button onclick="disconnect()" class="btn-danger">Отключить</button>
            </div>
            
            <!-- Create Alert -->
            <div class="section">
                <h3>📝 Создать алерт</h3>
                <div class="form-group">
                    <label>Выражение:</label>
                    <input type="text" id="alertExpression" placeholder="price > 5 300 60" />
                </div>
                <button onclick="createAlert()" class="btn-success">Создать</button>
                <button onclick="openHelpModal()" class="help-btn" style="width: 100%; margin-top: 10px;">
                    📚 Справочник синтаксиса
                </button>
                
                <div class="examples">
                      <strong>Примеры:</strong><br>
                        • <code>price > 5 300 60</code> — окно 300с, опрос каждые 60с<br>
                        • <code>volume > 1000000 10800 60</code> — объём за 3ч, опрос каждую минуту<br>
                        • <code>price > 5 300 60 & volume > 1000000 60</code><br>
                        • <code>volume_change > 50 1800 60</code><br>
                        • <code>price > 5 300 60 | oi > 200</code><br>
                </div>
            </div>
            
            <!-- My Alerts -->
            <div class="section">
                <h3>📋 Мои алерты</h3>
                <button onclick="loadMyAlerts()">Обновить</button>
                <button onclick="deleteAllAlerts()" class="btn-danger">Удалить все</button>
                
                <div id="myAlertsList" class="my-alerts-list">
                    <div class="no-alerts">
                        Нажмите "Обновить" для загрузки
                    </div>
                </div>
            </div>
            
            <!-- WebSocket Commands -->
            <div class="section">
                <h3>🔧 Команды</h3>
                <div class="ws-commands">
                    <button onclick="sendPing()">Ping</button>
                    <button onclick="getStatus()">Статус</button>
                </div>
            </div>
        </div>
        
        <!-- Main Content -->
        <div class="main-content">
            <!-- Header -->
            <div class="header">
                <h1>🚨 Alerts Dashboard</h1>
                <div class="header-controls">
                    <button class="help-btn" onclick="openHelpModal()">
                        📚 Справочник
                    </button>
                    <div>
                        <span>Статус: </span>
                        <span id="status" class="status-indicator disconnected">Отключено</span>
                    </div>
                </div>
            </div>
            
            <!-- Stats -->
            <div class="section">
                <div class="stats-grid">
                    <div class="stat-card">
                        <div class="stat-value" id="activeAlertsCount">0</div>
                        <div class="stat-label">Активных алертов</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value" id="triggeredCount">0</div>
                        <div class="stat-label">Сработало сегодня</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value" id="connectedUsers">0</div>
                        <div class="stat-label">Подключено пользователей</div>
                    </div>
                </div>
            </div>
            
            <!-- Triggered Alerts -->
            <div class="section">
                <h3>🔔 Сработавшие алерты</h3>
                <div id="triggeredAlerts" class="triggered-alerts">
                    <div class="no-alerts">
                        Здесь будут отображаться сработавшие алерты
                    </div>
                </div>
            </div>
            
            <!-- Active Alerts Grid -->
            <div class="section">
                <h3>📊 Активные алерты</h3>
                <div id="alertsGrid" class="alerts-grid">
                    <div class="no-alerts">
                        Создайте первый алерт для начала работы
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        let ws = null;
        let userId = null;
        let myAlerts = [];
        let triggeredToday = 0;
        let connectedUsers = 0;
        let alertBlacklists = {}; // alertId -> Set of blacklisted tickers

        // Modal Functions
        function openHelpModal() {
            document.getElementById('helpModal').style.display = 'block';
            document.body.style.overflow = 'hidden';
        }

        function closeHelpModal() {
            document.getElementById('helpModal').style.display = 'none';
            document.body.style.overflow = 'auto';
        }

        function copyToClipboardModal(text) {
            navigator.clipboard.writeText(text).then(function() {
                showSystemMessage('Скопировано: ' + text, 'success');
            }).catch(function(err) {
                showSystemMessage('Ошибка копирования', 'error');
            });
        }

        // Close modal when clicking outside
        window.onclick = function(event) {
            const modal = document.getElementById('helpModal');
            if (event.target === modal) {
                closeHelpModal();
            }
        }

        // Close modal with Escape key
        document.addEventListener('keydown', function(event) {
            if (event.key === 'Escape') {
                closeHelpModal();
            }
        });

        // Load blacklists from localStorage
        function loadBlacklists() {
            const saved = localStorage.getItem('alertBlacklists');
            if (saved) {
                try {
                    const parsed = JSON.parse(saved);
                    alertBlacklists = {};
                    for (const [alertId, tickers] of Object.entries(parsed)) {
                        alertBlacklists[alertId] = new Set(tickers);
                    }
                } catch (e) {
                    alertBlacklists = {};
                }
            }
        }

        // Save blacklists to localStorage
        function saveBlacklists() {
            const toSave = {};
            for (const [alertId, tickerSet] of Object.entries(alertBlacklists)) {
                toSave[alertId] = Array.from(tickerSet);
            }
            localStorage.setItem('alertBlacklists', JSON.stringify(toSave));
        }

        // WebSocket Management
        function connect() {
            userId = document.getElementById('userId').value;
            if (!userId) {
                alert('Введите User ID');
                return;
            }

            if (ws) {
                ws.close();
            }

            // Request notification permission
            if (Notification.permission === 'default') {
                Notification.requestPermission();
            }

            ws = new WebSocket(`ws://${window.location.host}/ws/alerts/${userId}`);
            
            ws.onopen = function() {
                updateConnectionStatus(true);
                showSystemMessage('Подключено к WebSocket', 'success');
                loadMyAlerts();
            };

            ws.onmessage = function(event) {
                const data = JSON.parse(event.data);
                handleWebSocketMessage(data);
            };

            ws.onclose = function() {
                updateConnectionStatus(false);
                showSystemMessage('Отключено от WebSocket', 'error');
            };

            ws.onerror = function(error) {
                showSystemMessage('WebSocket error: ' + error, 'error');
            };
        }

        function disconnect() {
            if (ws) {
                ws.close();
                ws = null;
            }
        }

        function updateConnectionStatus(connected) {
            const statusEl = document.getElementById('status');
            if (connected) {
                statusEl.textContent = 'Подключено';
                statusEl.className = 'status-indicator connected';
            } else {
                statusEl.textContent = 'Отключено';
                statusEl.className = 'status-indicator disconnected';
            }
        }

        // WebSocket Message Handling
        function handleWebSocketMessage(data) {
            switch(data.type) {
                case 'alert':
                    handleAlertTriggered(data);
                    break;
                case 'alert_created':
                    showSystemMessage('Алерт создан: ' + data.expression, 'success');
                    loadMyAlerts();
                    break;
                case 'alert_deleted':
                case 'all_alerts_deleted':
                    showSystemMessage('Алерт удален', 'success');
                    loadMyAlerts();
                    break;
                case 'status':
                    updateStats(data);
                    break;
                case 'connected':
                    showSystemMessage('Подключен к системе алертов', 'success');
                    break;
                case 'user_stats':
                    updateActiveAlertsCount(data.alerts_count);
                    break;
                case 'pong':
                    showSystemMessage('Pong получен', 'info');
                    break;
                default:
                    console.log('Unknown message type:', data);
            }
        }

        function handleAlertTriggered(data) {
            // Filter tickers based on blacklist
            const filteredData = filterAlertByBlacklist(data);
            
            // Only show alert if there are tickers left after filtering
            if (filteredData.tickers && filteredData.tickers.length > 0) {
                // Add to triggered alerts
                addTriggeredAlert(filteredData);
                
                // Highlight the triggered alert card
                highlightAlertCard(data.alert_id);
                
                // Update counter
                triggeredToday++;
                updateTriggeredCount();
                
                // Show browser notification
                if (Notification.permission === 'granted') {
                    new Notification('🚨 Алерт сработал!', {
                        body: `${filteredData.tickers.join(', ')}: ${data.readable_expression}`,
                        icon: '🚨'
                    });
                }
            } else {
                // All tickers were filtered out
                console.log('Alert filtered out completely:', data.alert_id);
                addFilteredAlert(data);
            }
        }

        function filterAlertByBlacklist(alertData) {
            const alertId = alertData.alert_id;
            const blacklist = alertBlacklists[alertId] || new Set();
            
            if (!alertData.tickers || blacklist.size === 0) {
                return alertData;
            }

            const filteredTickers = alertData.tickers.filter(ticker => !blacklist.has(ticker));
            
            return {
                ...alertData,
                tickers: filteredTickers,
                filtered: filteredTickers.length !== alertData.tickers.length,
                originalTickers: alertData.tickers,
                filteredOutTickers: alertData.tickers.filter(ticker => blacklist.has(ticker))
            };
        }

        function addTriggeredAlert(data) {
            const container = document.getElementById('triggeredAlerts');
            
            // Remove "no alerts" message if present
            if (container.querySelector('.no-alerts')) {
                container.innerHTML = '';
            }
            
            const alertEl = document.createElement('div');
            alertEl.className = 'triggered-alert';
            
            let content = `
                <div class="triggered-header">
                    <strong>🚨 АЛЕРТ СРАБОТАЛ!</strong>
                    <div class="triggered-time">${new Date(data.timestamp).toLocaleTimeString()}</div>
                </div>
                <div class="alert-expression">${data.readable_expression}</div>
                <div class="triggered-tickers">
                    ${data.tickers?.map(ticker => `<span class="ticker-badge">${ticker}</span>`).join('') || ''}
                </div>
            `;

            if (data.filtered) {
                content += `
                    <div class="filtered-info">
                        ℹ️ Отфильтровано: ${data.filteredOutTickers.join(', ')} (в блеклисте)
                    </div>
                `;
            }

            content += `<div style="font-size: 12px; color: #666;">ID: ${data.alert_id}</div>`;
            
            alertEl.innerHTML = content;
            
            // Insert at the beginning
            container.insertBefore(alertEl, container.firstChild);
            
            // Remove old alerts (keep only last 10)
            const alerts = container.querySelectorAll('.triggered-alert');
            if (alerts.length > 10) {
                alerts[alerts.length - 1].remove();
            }
        }

        function addFilteredAlert(data) {
            const container = document.getElementById('triggeredAlerts');
            
            // Remove "no alerts" message if present
            if (container.querySelector('.no-alerts')) {
                container.innerHTML = '';
            }
            
            const alertEl = document.createElement('div');
            alertEl.className = 'triggered-alert filtered';
            alertEl.innerHTML = `
                <div class="triggered-header">
                    <strong>⚠️ АЛЕРТ ОТФИЛЬТРОВАН</strong>
                    <div class="triggered-time">${new Date(data.timestamp).toLocaleTimeString()}</div>
                </div>
                <div class="alert-expression">${data.readable_expression}</div>
                <div class="triggered-tickers">
                    ${data.tickers?.map(ticker => `<span class="ticker-badge filtered">${ticker}</span>`).join('') || ''}
                </div>
                <div class="filtered-info">
                    🚫 Все тикеры (${data.tickers?.length || 0}) находятся в блеклисте для этого алерта
                </div>
                <div style="font-size: 12px; color: #666;">ID: ${data.alert_id}</div>
            `;
            
            // Insert at the beginning
            container.insertBefore(alertEl, container.firstChild);
            
            // Remove old alerts (keep only last 10)
            const alerts = container.querySelectorAll('.triggered-alert');
            if (alerts.length > 10) {
                alerts[alerts.length - 1].remove();
            }
        }

        function highlightAlertCard(alertId) {
            const cards = document.querySelectorAll('.alert-card');
            cards.forEach(card => {
                if (card.dataset.alertId === alertId) {
                    card.classList.add('triggered');
                    setTimeout(() => {
                        card.classList.remove('triggered');
                    }, 3000);
                }
            });
        }

        // Blacklist Management
        function addToBlacklist(alertId, ticker) {
            ticker = ticker.trim().toUpperCase();
            if (!ticker) return;

            if (!alertBlacklists[alertId]) {
                alertBlacklists[alertId] = new Set();
            }
            
            alertBlacklists[alertId].add(ticker);
            saveBlacklists();
            updateBlacklistDisplay(alertId);
            showSystemMessage(`Тикер ${ticker} добавлен в блеклист`, 'info');
        }

        function removeFromBlacklist(alertId, ticker) {
            if (alertBlacklists[alertId]) {
                alertBlacklists[alertId].delete(ticker);
                if (alertBlacklists[alertId].size === 0) {
                    delete alertBlacklists[alertId];
                }
                saveBlacklists();
                updateBlacklistDisplay(alertId);
                showSystemMessage(`Тикер ${ticker} удален из блеклиста`, 'info');
            }
        }

        function updateBlacklistDisplay(alertId) {
            const card = document.querySelector(`[data-alert-id="${alertId}"]`);
            if (!card) return;

            const blacklistTags = card.querySelector('.blacklist-tags');
            const blacklistCount = card.querySelector('.blacklist-count');
            
            if (!blacklistTags || !blacklistCount) return;

            const blacklist = alertBlacklists[alertId] || new Set();
            
            // Update count
            blacklistCount.textContent = blacklist.size > 0 ? `${blacklist.size} тикеров` : 'пусто';
            
            // Update tags
            if (blacklist.size === 0) {
                blacklistTags.innerHTML = '<span style="color: #999; font-size: 11px;">Нет заблокированных тикеров</span>';
            } else {
                blacklistTags.innerHTML = Array.from(blacklist).map(ticker => `
                    <span class="blacklist-tag">
                        ${ticker}
                        <span class="remove-btn" onclick="removeFromBlacklist('${alertId}', '${ticker}')">&times;</span>
                    </span>
                `).join('');
            }
        }

        // Alert Management
        async function createAlert() {
            const expression = document.getElementById('alertExpression').value.trim();
            if (!expression) {
                alert('Введите выражение алерта');
                return;
            }

            if (!userId) {
                alert('Сначала подключитесь');
                return;
            }

            try {
                const response = await fetch('/alerts', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        expression: expression,
                        user_id: userId
                    })
                });

                const result = await response.json();
                
                if (response.ok) {
                    showSystemMessage('Алерт создан: ' + result.expression, 'success');
                    document.getElementById('alertExpression').value = '';
                    loadMyAlerts();
                } else {
                    showSystemMessage('Ошибка: ' + result.detail, 'error');
                }
            } catch (error) {
                showSystemMessage('Ошибка создания алерта: ' + error.message, 'error');
            }
        }

        async function loadMyAlerts() {
            if (!userId) return;

            try {
                const response = await fetch(`/alerts?user_id=${userId}`);
                const alerts = await response.json();
                myAlerts = alerts;
                displayMyAlerts(alerts);
                displayAlertsGrid(alerts);
                updateActiveAlertsCount(alerts.length);
            } catch (error) {
                showSystemMessage('Ошибка загрузки алертов: ' + error.message, 'error');
            }
        }

        function displayMyAlerts(alerts) {
            const container = document.getElementById('myAlertsList');
            
            if (alerts.length === 0) {
                container.innerHTML = '<div class="no-alerts">Нет активных алертов</div>';
                return;
            }

            const alertsHtml = alerts.map(alert => {
                const blacklist = alertBlacklists[alert.alert_id] || new Set();
                return `
                    <div class="alert-card" style="margin-bottom: 10px; padding: 15px;">
                        <div class="alert-id">${alert.alert_id}</div>
                        <div class="alert-expression">${alert.expression}</div>
                        <div class="alert-stats">
                            <span>Подписчиков: ${alert.subscribers_count}</span>
                            <span>${alert.is_websocket_connected ? '🟢' : '🔴'}</span>
                        </div>
                        ${blacklist.size > 0 ? `
                            <div style="font-size: 11px; color: #666; margin: 5px 0;">
                                🚫 Блеклист: ${Array.from(blacklist).join(', ')}
                            </div>
                        ` : ''}
                        <button onclick="deleteAlert('${alert.alert_id}')" class="btn-danger" style="width: 100%; margin-top: 10px;">
                            Удалить
                        </button>
                    </div>
                `;
            }).join('');

            container.innerHTML = alertsHtml;
        }

        function displayAlertsGrid(alerts) {
            const container = document.getElementById('alertsGrid');
            
            if (alerts.length === 0) {
                container.innerHTML = '<div class="no-alerts">Создайте первый алерт для начала работы</div>';
                return;
            }

            const alertsHtml = alerts.map(alert => {
                const blacklist = alertBlacklists[alert.alert_id] || new Set();
                return `
                    <div class="alert-card" data-alert-id="${alert.alert_id}">
                        <div class="alert-header">
                            <h4>Алерт</h4>
                            <div class="alert-id">${alert.alert_id}</div>
                        </div>
                        <div class="alert-expression">${alert.expression}</div>
                        <div class="alert-stats">
                            <span>👥 ${alert.subscribers_count}</span>
                            <span>${alert.is_websocket_connected ? '🟢 Подключен' : '🔴 Отключен'}</span>
                        </div>
                        
                        <div class="blacklist-section">
                            <div class="blacklist-header">
                                <span class="blacklist-title">🚫 Блеклист тикеров</span>
                                <span class="blacklist-count">${blacklist.size > 0 ? `${blacklist.size} тикеров` : 'пусто'}</span>
                            </div>
                            <div class="blacklist-tags">
                                ${blacklist.size === 0 ? 
                                    '<span style="color: #999; font-size: 11px;">Нет заблокированных тикеров</span>' :
                                    Array.from(blacklist).map(ticker => `
                                        <span class="blacklist-tag">
                                            ${ticker}
                                            <span class="remove-btn" onclick="removeFromBlacklist('${alert.alert_id}', '${ticker}')">&times;</span>
                                        </span>
                                    `).join('')
                                }
                            </div>
                            <div class="blacklist-input-row">
                                <input type="text" class="blacklist-input" placeholder="BTC" onkeypress="handleBlacklistKeypress(event, '${alert.alert_id}')">
                                <button class="add-blacklist-btn" onclick="addTickerToBlacklist('${alert.alert_id}')">+</button>
                            </div>
                        </div>
                        
                        <div class="alert-actions">
                            <button onclick="deleteAlert('${alert.alert_id}')" class="btn-danger">
                                🗑️ Удалить
                            </button>
                        </div>
                    </div>
                `;
            }).join('');

            container.innerHTML = alertsHtml;
        }

        function handleBlacklistKeypress(event, alertId) {
            if (event.key === 'Enter') {
                addTickerToBlacklist(alertId);
            }
        }

        function addTickerToBlacklist(alertId) {
            const card = document.querySelector(`[data-alert-id="${alertId}"]`);
            if (!card) return;

            const input = card.querySelector('.blacklist-input');
            const ticker = input.value.trim().toUpperCase();
            
            if (ticker) {
                addToBlacklist(alertId, ticker);
                input.value = '';
            }
        }

        async function deleteAlert(alertId) {
            if (!userId) return;

            try {
                const response = await fetch(`/alerts/${alertId}?user_id=${userId}`, {
                    method: 'DELETE'
                });

                const result = await response.json();
                
                if (response.ok) {
                    showSystemMessage('Алерт удален: ' + alertId, 'success');
                    // Clean up blacklist
                    delete alertBlacklists[alertId];
                    saveBlacklists();
                    loadMyAlerts();
                } else {
                    showSystemMessage('Ошибка: ' + result.detail, 'error');
                }
            } catch (error) {
                showSystemMessage('Ошибка удаления алерта: ' + error.message, 'error');
            }
        }

        async function deleteAllAlerts() {
            if (!userId) return;
            
            if (!confirm('Вы уверены, что хотите удалить все алерты?')) {
                return;
            }

            try {
                const response = await fetch(`/alerts?user_id=${userId}`, {
                    method: 'DELETE'
                });

                const result = await response.json();
                
                if (response.ok) {
                    showSystemMessage(`Удалено алертов: ${result.removed_count}`, 'success');
                    // Clean up all blacklists for this user
                    alertBlacklists = {};
                    saveBlacklists();
                    loadMyAlerts();
                } else {
                    showSystemMessage('Ошибка: ' + result.detail, 'error');
                }
            } catch (error) {
                showSystemMessage('Ошибка удаления всех алертов: ' + error.message, 'error');
            }
        }

        // WebSocket Commands
        function sendPing() {
            if (ws && ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify({type: 'ping'}));
            }
        }

        function getStatus() {
            if (ws && ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify({type: 'get_status'}));
            }
        }

        // UI Updates
        function updateStats(data) {
            connectedUsers = data.connected_users || 0;
            document.getElementById('connectedUsers').textContent = connectedUsers;
            showSystemMessage(`Статус обновлен: ${data.your_alerts} ваших алертов, ${data.total_alerts} всего`, 'info');
        }

        function updateActiveAlertsCount(count) {
            document.getElementById('activeAlertsCount').textContent = count;
        }

        function updateTriggeredCount() {
            document.getElementById('triggeredCount').textContent = triggeredToday;
        }

        function showSystemMessage(message, type) {
            // Simple toast notification
            const toast = document.createElement('div');
            toast.style.cssText = `
                position: fixed;
                top: 20px;
                right: 20px;
                background: ${type === 'success' ? '#4CAF50' : type === 'error' ? '#f44336' : '#2196F3'};
                color: white;
                padding: 12px 20px;
                border-radius: 8px;
                box-shadow: 0 4px 15px rgba(0,0,0,0.2);
                z-index: 9999;
                max-width: 300px;
                word-wrap: break-word;
                animation: slideIn 0.3s ease-out;
            `;
            toast.textContent = message;
            
            document.body.appendChild(toast);
            
            setTimeout(() => {
                toast.style.animation = 'slideOut 0.3s ease-in forwards';
                setTimeout(() => {
                    if (toast.parentNode) {
                        toast.parentNode.removeChild(toast);
                    }
                }, 300);
            }, 3000);
        }

        // Add CSS animations for toast
        const style = document.createElement('style');
        style.textContent = `
            @keyframes slideIn {
                from { transform: translateX(100%); opacity: 0; }
                to { transform: translateX(0); opacity: 1; }
            }
            @keyframes slideOut {
                from { transform: translateX(0); opacity: 1; }
                to { transform: translateX(100%); opacity: 0; }
            }
        `;
        document.head.appendChild(style);

        // Initialize on page load
        document.addEventListener('DOMContentLoaded', function() {
            loadBlacklists();
            updateTriggeredCount();
            document.getElementById('connectedUsers').textContent = connectedUsers;
        });
    </script>
</body>
</html>
"""
    return HTMLResponse(content=html)