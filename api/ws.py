import json
import datetime as dt
from fastapi import FastAPI, APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import HTMLResponse
from config import logger

from modules.composite.manager import CompositeListenerManager
from .websocket_manager import WebSocketManager

app = FastAPI()
router = APIRouter()


@app.websocket("/alerts/{user_id}")
async def websocket_alerts_endpoint(websocket: WebSocket, user_id: int):
    """
    WebSocket endpoint для получения алертов.
    Один WebSocket на пользователя.
    
    Args:
        websocket (WebSocket): WebSocket соединение
        user_id (int): ID пользователя
    """
    await WebSocketManager.instance().connect(websocket, user_id)
    
    try:
        # Отправляем приветственное сообщение
        await websocket.send_text(json.dumps({
            "type": "connected",
            "message": "Подключен к системе алертов",
            "user_id": user_id,
            "timestamp": dt.datetime.utcnow().isoformat()
        }, ensure_ascii=False))
        
        # Отправляем статистику по алертам пользователя
        user_subscriptions = CompositeListenerManager.instance().get_user_subscriptions(user_id)
        await websocket.send_text(json.dumps({
            "type": "user_stats",
            "alerts_count": len(user_subscriptions),
            "alert_ids": list(user_subscriptions.keys()),
            "timestamp": dt.datetime.utcnow().isoformat()
        }, ensure_ascii=False))
        
        # Слушаем сообщения от клиента (для keep-alive и команд)
        while True:
            try:
                data = await websocket.receive_text()
                message = json.loads(data)
                
                # Обработка ping для keep-alive
                if message.get("type") == "ping":
                    await websocket.send_text(json.dumps({
                        "type": "pong",
                        "timestamp": dt.datetime.utcnow().isoformat()
                    }, ensure_ascii=False))
                
                # Получить статус соединения
                elif message.get("type") == "get_status":
                    user_subs = CompositeListenerManager.instance().get_user_subscriptions(user_id)
                    await websocket.send_text(json.dumps({
                        "type": "status",
                        "connected_users": len(WebSocketManager.instance().get_connected_users()),
                        "your_alerts": len(user_subs),
                        "total_alerts": len(CompositeListenerManager.instance().all_alerts),
                        "timestamp": dt.datetime.utcnow().isoformat()
                    }, ensure_ascii=False))
                
                # Получить список своих алертов
                elif message.get("type") == "get_my_alerts":
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
                
                # Неизвестная команда
                else:
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "message": f"Неизвестная команда: {message.get('type')}",
                        "timestamp": dt.datetime.utcnow().isoformat()
                    }, ensure_ascii=False))
                    
            except json.JSONDecodeError:
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "message": "Неверный формат JSON",
                    "timestamp": dt.datetime.utcnow().isoformat()
                }, ensure_ascii=False))
            except WebSocketDisconnect:
                break
            except Exception as exc:
                logger.error(f"[WS] Ошибка обработки сообщения от {user_id}: {exc}")
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "message": "Внутренняя ошибка сервера",
                    "timestamp": dt.datetime.utcnow().isoformat()
                }, ensure_ascii=False))
                
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.error(f"[WS] Критическая ошибка для пользователя {user_id}: {exc}")
    finally:
        await WebSocketManager.instance().disconnect(user_id)


@app.get("/ws/status")
async def get_websocket_status():
    """Статус WebSocket соединений"""
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


@app.post("/ws/test-alert/{user_id}")
async def send_test_alert(user_id: int, message: str = "Тестовый алерт"):
    """Отправка тестового алерта для проверки соединения"""
    if not WebSocketManager.instance().is_connected(user_id):
        raise HTTPException(status_code=404, detail=f"Пользователь {user_id} не подключен")
    
    test_data = {
        "type": "test_alert",
        "message": message,
        "tickers": ["TESTUSDT"],
        "timestamp": dt.datetime.utcnow().isoformat()
    }
    
    success = await WebSocketManager.instance().send_alert(user_id, test_data)
    return {
        "sent": success,
        "user_id": user_id,
        "message": message
    }


@app.post("/ws/broadcast-message")
async def broadcast_message(message: str, message_type: str = "announcement"):
    """Отправка сообщения всем подключенным пользователям"""
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
async def get_demo_page():
    """Демо-страница для тестирования WebSocket соединения"""
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>WebSocket Alerts Demo</title>
        <style>
            body { 
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; 
                margin: 20px; 
                background-color: #f5f5f5; 
            }
            .container { 
                max-width: 1000px; 
                margin: 0 auto; 
                background: white; 
                padding: 20px; 
                border-radius: 8px; 
                box-shadow: 0 2px 10px rgba(0,0,0,0.1); 
            }
            .header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                margin-bottom: 20px;
                padding-bottom: 10px;
                border-bottom: 2px solid #e0e0e0;
            }
            .section {
                margin: 20px 0;
                padding: 15px;
                border: 1px solid #e0e0e0;
                border-radius: 5px;
                background: #fafafa;
            }
            .section h3 {
                margin-top: 0;
                color: #333;
            }
            .messages { 
                border: 1px solid #ccc; 
                height: 400px; 
                overflow-y: scroll; 
                padding: 10px; 
                margin: 10px 0; 
                background: white;
                border-radius: 5px;
            }
            .message { 
                margin: 5px 0; 
                padding: 8px; 
                border-radius: 4px; 
                word-wrap: break-word;
            }
            .alert { 
                background-color: #ffebee; 
                border-left: 4px solid #f44336; 
                animation: alertPulse 2s ease-in-out;
            }
            .alert-created { 
                background-color: #e8f5e8; 
                border-left: 4px solid #4caf50; 
            }
            .alert-deleted { 
                background-color: #fff3e0; 
                border-left: 4px solid #ff9800; 
            }
            .system { 
                background-color: #e3f2fd; 
                border-left: 4px solid #2196f3; 
            }
            .error { 
                background-color: #ffebee; 
                border-left: 4px solid #f44336; 
            }
            .status { 
                background-color: #f3e5f5; 
                border-left: 4px solid #9c27b0; 
            }
            
            @keyframes alertPulse {
                0% { transform: scale(1); }
                50% { transform: scale(1.02); box-shadow: 0 0 15px rgba(244, 67, 54, 0.3); }
                100% { transform: scale(1); }
            }
            
            input, button, select, textarea { 
                padding: 8px 12px; 
                margin: 5px; 
                border: 1px solid #ddd;
                border-radius: 4px;
                font-size: 14px;
            }
            button { 
                cursor: pointer; 
                background: #2196f3;
                color: white;
                border: none;
                transition: background 0.3s;
            }
            button:hover {
                background: #1976d2;
            }
            button.danger {
                background: #f44336;
            }
            button.danger:hover {
                background: #d32f2f;
            }
            button.success {
                background: #4caf50;
            }
            button.success:hover {
                background: #388e3c;
            }
            .status-indicator {
                padding: 5px 10px;
                border-radius: 15px;
                color: white;
                font-weight: bold;
            }
            .connected { background: #4caf50; }
            .disconnected { background: #f44336; }
            
            .form-group {
                margin: 10px 0;
            }
            .form-group label {
                display: block;
                margin-bottom: 5px;
                font-weight: bold;
            }
            .form-group input, .form-group textarea {
                width: 100%;
                max-width: 400px;
            }
            .examples {
                background: #f0f7ff;
                padding: 10px;
                border-radius: 4px;
                margin: 10px 0;
                font-size: 12px;
            }
            .examples strong {
                color: #1976d2;
            }
            
            .alerts-list {
                max-height: 200px;
                overflow-y: auto;
                border: 1px solid #ddd;
                border-radius: 4px;
                background: white;
            }
            .alert-item {
                display: flex;
                justify-content: space-between;
                align-items: center;
                padding: 10px;
                border-bottom: 1px solid #eee;
            }
            .alert-item:last-child {
                border-bottom: none;
            }
            .alert-expression {
                font-family: monospace;
                background: #f5f5f5;
                padding: 4px 8px;
                border-radius: 3px;
                flex-grow: 1;
                margin-right: 10px;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🚨 WebSocket Alerts Demo</h1>
                <div>
                    <span>Статус: </span>
                    <span id="status" class="status-indicator disconnected">Отключено</span>
                </div>
            </div>
            
            <!-- Подключение -->
            <div class="section">
                <h3>🔌 Подключение</h3>
                <div class="form-group">
                    <label>User ID:</label>
                    <input type="number" id="userId" value="12345" />
                    <button onclick="connect()" class="success">Подключить</button>
                    <button onclick="disconnect()" class="danger">Отключить</button>
                </div>
            </div>
            
            <!-- Управление алертами -->
            <div class="section">
                <h3>📝 Создание алертов</h3>
                <div class="form-group">
                    <label>Выражение алерта:</label>
                    <input type="text" id="alertExpression" placeholder="price > 5 300" />
                    <button onclick="createAlert()" class="success">Создать алерт</button>
                </div>
                <div class="examples">
                    <strong>Примеры выражений:</strong><br>
                    • <code>price > 5 300</code> — цена выросла больше чем на 5% за 300 секунд<br>
                    • <code>volume > 50 60</code> — объём вырос больше чем на 50% за 60 секунд<br>
                    • <code>oi < 20</code> — открытый интерес упал больше чем на 20%<br>
                    • <code>funding > 0.1 600</code> — funding ставка больше 0.1% за 600 секунд до расчёта<br>
                    • <code>price > 5 300 & oi < 100 @10</code> — композитный: цена И OI с кулдауном 10 сек
                </div>
            </div>
            
            <!-- Мои алерты -->
            <div class="section">
                <h3>📋 Мои алерты</h3>
                <button onclick="loadMyAlerts()">Обновить список</button>
                <button onclick="deleteAllAlerts()" class="danger">Удалить все</button>
                <div id="alertsList" class="alerts-list">
                    <div style="padding: 20px; text-align: center; color: #666;">
                        Нажмите "Обновить список" для загрузки алертов
                    </div>
                </div>
            </div>
            
            <!-- WebSocket команды -->
            <div class="section">
                <h3>🔧 WebSocket команды</h3>
                <button onclick="sendPing()">Ping</button>
                <button onclick="getStatus()">Статус</button>
                <button onclick="getMyAlerts()">Мои алерты (WS)</button>
            </div>
            
            <!-- Сообщения -->
            <div class="section">
                <h3>💬 Сообщения</h3>
                <button onclick="clearMessages()">Очистить</button>
                <div id="messages" class="messages"></div>
            </div>
        </div>

        <script>
            let ws = null;
            let userId = null;
            let myAlerts = [];

            function addMessage(message, type = 'system') {
                const messages = document.getElementById('messages');
                const div = document.createElement('div');
                div.className = `message ${type}`;
                
                const time = new Date().toLocaleTimeString();
                let content = '';
                
                if (type === 'alert') {
                    // Специальное форматирование для алертов
                    content = `<strong>🚨 АЛЕРТ СРАБОТАЛ!</strong><br>
                               <strong>Тикеры:</strong> ${message.tickers?.join(', ') || 'N/A'}<br>
                               <strong>Условие:</strong> ${message.expression}<br>
                               <strong>ID:</strong> ${message.alert_id}<br>
                               <strong>Время:</strong> ${new Date(message.timestamp).toLocaleString()}`;
                } else if (type === 'alert-created') {
                    content = `<strong>✅ Алерт создан!</strong><br>
                               <strong>Условие:</strong> ${message.expression}<br>
                               <strong>ID:</strong> ${message.alert_id}<br>
                               <strong>Сообщение:</strong> ${message.message}`;
                } else if (type === 'alert-deleted') {
                    content = `<strong>🗑️ Алерт удален!</strong><br>
                               <strong>ID:</strong> ${message.alert_id}<br>
                               <strong>Сообщение:</strong> ${message.message}`;
                } else if (type === 'status') {
                    content = `<strong>📊 Статус:</strong><br>
                               <strong>Подключено пользователей:</strong> ${message.connected_users}<br>
                               <strong>Ваших алертов:</strong> ${message.your_alerts}<br>
                               <strong>Всего алертов:</strong> ${message.total_alerts}`;
                } else {
                    content = JSON.stringify(message, null, 2);
                }
                
                div.innerHTML = `<strong>[${time}]</strong> ${content}`;
                messages.appendChild(div);
                messages.scrollTop = messages.scrollHeight;
                
                // Если это алерт, показываем уведомление браузера
                if (type === 'alert' && Notification.permission === 'granted') {
                    new Notification('🚨 Алерт сработал!', {
                        body: `${message.tickers?.join(', ')}: ${message.expression}`,
                        icon: '🚨'
                    });
                }
            }

            function connect() {
                userId = document.getElementById('userId').value;
                if (!userId) {
                    alert('Введите User ID');
                    return;
                }

                if (ws) {
                    ws.close();
                }

                // Запрашиваем разрешение на уведомления
                if (Notification.permission === 'default') {
                    Notification.requestPermission();
                }

                ws = new WebSocket(`ws://localhost:8000/ws/alerts/${userId}`);
                
                ws.onopen = function() {
                    document.getElementById('status').textContent = 'Подключено';
                    document.getElementById('status').className = 'status-indicator connected';
                    addMessage({message: 'Подключено к WebSocket'}, 'system');
                    loadMyAlerts(); // Автоматически загружаем алерты при подключении
                };

                ws.onmessage = function(event) {
                    const data = JSON.parse(event.data);
                    let messageType = 'system';
                    
                    switch(data.type) {
                        case 'alert':
                            messageType = 'alert';
                            break;
                        case 'alert_created':
                            messageType = 'alert-created';
                            loadMyAlerts(); // Обновляем список алертов
                            break;
                        case 'alert_deleted':
                        case 'all_alerts_deleted':
                            messageType = 'alert-deleted';
                            loadMyAlerts(); // Обновляем список алертов
                            break;
                        case 'status':
                            messageType = 'status';
                            break;
                        case 'error':
                            messageType = 'error';
                            break;
                    }
                    
                    addMessage(data, messageType);
                };

                ws.onclose = function() {
                    document.getElementById('status').textContent = 'Отключено';
                    document.getElementById('status').className = 'status-indicator disconnected';
                    addMessage({message: 'Отключено от WebSocket'}, 'system');
                };

                ws.onerror = function(error) {
                    addMessage({error: 'WebSocket error: ' + error}, 'error');
                };
            }

            function disconnect() {
                if (ws) {
                    ws.close();
                    ws = null;
                }
            }

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

            function getMyAlerts() {
                if (ws && ws.readyState === WebSocket.OPEN) {
                    ws.send(JSON.stringify({type: 'get_my_alerts'}));
                }
            }

            function clearMessages() {
                document.getElementById('messages').innerHTML = '';
            }

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
                        addMessage({
                            message: `Алерт создан: ${result.expression}`,
                            alert_id: result.alert_id
                        }, 'alert-created');
                        document.getElementById('alertExpression').value = '';
                        loadMyAlerts();
                    } else {
                        addMessage({error: `Ошибка: ${result.detail}`}, 'error');
                    }
                } catch (error) {
                    addMessage({error: `Ошибка создания алерта: ${error.message}`}, 'error');
                }
            }

            async function loadMyAlerts() {
                if (!userId) return;

                try {
                    const response = await fetch(`/alerts?user_id=${userId}`);
                    const alerts = await response.json();
                    myAlerts = alerts;
                    displayAlerts(alerts);
                } catch (error) {
                    addMessage({error: `Ошибка загрузки алертов: ${error.message}`}, 'error');
                }
            }

            function displayAlerts(alerts) {
                const alertsList = document.getElementById('alertsList');
                
                if (alerts.length === 0) {
                    alertsList.innerHTML = '<div style="padding: 20px; text-align: center; color: #666;">Нет активных алертов</div>';
                    return;
                }

                const alertsHtml = alerts.map(alert => `
                    <div class="alert-item">
                        <div class="alert-expression">${alert.expression}</div>
                        <div>
                            <small>Подписчиков: ${alert.subscribers_count} | 
                            ${alert.is_websocket_connected ? '🟢 Подключен' : '🔴 Не подключен'}</small>
                            <button onclick="deleteAlert('${alert.alert_id}')" class="danger" style="margin-left: 10px;">Удалить</button>
                        </div>
                    </div>
                `).join('');

                alertsList.innerHTML = alertsHtml;
            }

            async function deleteAlert(alertId) {
                if (!userId) return;

                try {
                    const response = await fetch(`/alerts/${alertId}?user_id=${userId}`, {
                        method: 'DELETE'
                    });

                    const result = await response.json();
                    
                    if (response.ok) {
                        addMessage({
                            message: `Алерт удален: ${alertId}`,
                            alert_id: alertId
                        }, 'alert-deleted');
                        loadMyAlerts();
                    } else {
                        addMessage({error: `Ошибка: ${result.detail}`}, 'error');
                    }
                } catch (error) {
                    addMessage({error: `Ошибка удаления алерта: ${error.message}`}, 'error');
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
                        addMessage({
                            message: `Удалено алертов: ${result.removed_count}`,
                            removed_count: result.removed_count
                        }, 'alert-deleted');
                        loadMyAlerts();
                    } else {
                        addMessage({error: `Ошибка: ${result.detail}`}, 'error');
                    }
                } catch (error) {
                    addMessage({error: `Ошибка удаления всех алертов: ${error.message}`}, 'error');
                }
            }
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html)