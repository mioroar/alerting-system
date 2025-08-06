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
    
    Returns:
        HTMLResponse: HTML страница с JavaScript кодом для демонстрации
            WebSocket функциональности системы алертов.
            
    Note:
        Страница содержит полный интерфейс для тестирования всех
        возможностей WebSocket API, включая создание алертов,
        получение уведомлений и управление соединением.
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
        
        .alerts-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
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
        
        .triggered-alert {
            background: white;
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 15px;
            border-left: 4px solid #ff4444;
            box-shadow: 0 4px 20px rgba(255, 68, 68, 0.2);
            animation: newAlert 0.5s ease-out;
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
        }
    </style>
</head>
<body>
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
                    <input type="text" id="alertExpression" placeholder="price > 5 300" />
                </div>
                <button onclick="createAlert()" class="btn-success">Создать</button>
                
                <div class="examples">
                    <strong>Примеры:</strong><br>
                    • <code>price > 5 300</code><br>
                    • <code>price > 5 300 & volume > 1000000 60</code><br>
                    • <code>price > 5 300 & volume > 1000000 60 | oi > 200</code><br>
                    • <code>price > 5 300 & volume > 1000000 60 | oi > 200 @3600</code>
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
                <div>
                    <span>Статус: </span>
                    <span id="status" class="status-indicator disconnected">Отключено</span>
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
            // Add to triggered alerts
            addTriggeredAlert(data);
            
            // Highlight the triggered alert card
            highlightAlertCard(data.alert_id);
            
            // Update counter
            triggeredToday++;
            updateTriggeredCount();
            
            // Show browser notification
            if (Notification.permission === 'granted') {
                new Notification('🚨 Алерт сработал!', {
                    body: `${data.tickers?.join(', ')}: ${data.readable_expression}`,
                    icon: '🚨'
                });
            }
        }

        function addTriggeredAlert(data) {
            const container = document.getElementById('triggeredAlerts');
            
            // Remove "no alerts" message if present
            if (container.querySelector('.no-alerts')) {
                container.innerHTML = '';
            }
            
            const alertEl = document.createElement('div');
            alertEl.className = 'triggered-alert';
            alertEl.innerHTML = `
                <div class="triggered-header">
                    <strong>🚨 АЛЕРТ СРАБОТАЛ!</strong>
                    <div class="triggered-time">${new Date(data.timestamp).toLocaleTimeString()}</div>
                </div>
                <div class="alert-expression">${data.readable_expression}</div>
                <div class="triggered-tickers">
                    ${data.tickers?.map(ticker => `<span class="ticker-badge">${ticker}</span>`).join('') || ''}
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

            const alertsHtml = alerts.map(alert => `
                <div class="alert-card" style="margin-bottom: 10px; padding: 15px;">
                    <div class="alert-id">${alert.alert_id}</div>
                    <div class="alert-expression">${alert.expression}</div>
                    <div class="alert-stats">
                        <span>Подписчиков: ${alert.subscribers_count}</span>
                        <span>${alert.is_websocket_connected ? '🟢' : '🔴'}</span>
                    </div>
                    <button onclick="deleteAlert('${alert.alert_id}')" class="btn-danger" style="width: 100%; margin-top: 10px;">
                        Удалить
                    </button>
                </div>
            `).join('');

            container.innerHTML = alertsHtml;
        }

        function displayAlertsGrid(alerts) {
            const container = document.getElementById('alertsGrid');
            
            if (alerts.length === 0) {
                container.innerHTML = '<div class="no-alerts">Создайте первый алерт для начала работы</div>';
                return;
            }

            const alertsHtml = alerts.map(alert => `
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
                    <div class="alert-actions">
                        <button onclick="deleteAlert('${alert.alert_id}')" class="btn-danger">
                            🗑️ Удалить
                        </button>
                    </div>
                </div>
            `).join('');

            container.innerHTML = alertsHtml;
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
            updateTriggeredCount();
            document.getElementById('connectedUsers').textContent = connectedUsers;
        });
    </script>
</body>
</html>
    """
    return HTMLResponse(content=html)