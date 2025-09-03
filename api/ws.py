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

@router.get("/orders")
async def get_orders_page() -> HTMLResponse:
    html = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Карта плотностей ордеров</title>
    <script crossorigin src="https://unpkg.com/@msgpack/msgpack"></script>
    <style>
        :root {
            --bg-main: #0d0d0d;
            --bg-panel: #1a1a1a;
            --bg-input: #0d0d0d;
            --border-color: #2a2a2a;
            --text-primary: #e0e0e0;
            --text-secondary: #a0a0a0;
            --accent-green: #238636;
            --accent-red: #DA3633;
            --font-main: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif, "Apple Color Emoji", "Segoe UI Emoji";
        }

        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: var(--font-main);
            background: var(--bg-main);
            color: var(--text-primary);
            overflow: hidden;
            font-size: 13px;
        }

        .container {
            display: flex;
            height: 100vh;
        }

        /* --- Панель настроек --- */
        .settings-panel {
            width: 280px;
            min-width: 280px;
            background: var(--bg-panel);
            padding: 20px;
            overflow-y: auto;
            border-left: 1px solid var(--border-color);
            display: flex;
            flex-direction: column;
            flex-shrink: 0;
        }

        .settings-header {
            font-size: 16px;
            font-weight: 600;
            margin-bottom: 24px;
            color: var(--text-primary);
        }

        .settings-group {
            margin-bottom: 20px;
        }

        .settings-group h3 {
            font-size: 12px;
            color: var(--text-secondary);
            margin-bottom: 8px;
            text-transform: uppercase;
            font-weight: 600;
        }

        .input-group input,
        .input-group select,
        .blacklist-input-row input,
        .custom-ticker-row input {
            width: 100%;
            padding: 8px 12px;
            background: var(--bg-input);
            border: 1px solid var(--border-color);
            color: var(--text-primary);
            border-radius: 6px;
            font-size: 13px;
        }

        .input-group input:focus,
        .input-group select:focus,
        .blacklist-input-row input:focus,
        .custom-ticker-row input:focus {
            outline: none;
            border-color: #3a3a3a;
            background: #1a1a1a;
        }

        .multiplier-inputs {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 10px;
        }

        .multiplier-inputs input {
            text-align: center;
        }
        
        .blacklist-input-row, .custom-ticker-row {
            display: flex;
            gap: 8px;
            margin-bottom: 10px;
        }

        .btn-add {
            padding: 8px 16px;
            background-color: #2a2a2a;
            border: 1px solid var(--border-color);
            color: var(--text-primary);
            border-radius: 6px;
            cursor: pointer;
            font-weight: 600;
            white-space: nowrap;
        }

        .btn-add:hover {
            background-color: #3a3a3a;
        }

        #customTickersContainer, #blacklistTags {
            margin-top: 10px;
        }

        .custom-ticker-item, .blacklist-tag {
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 6px 10px;
            background: var(--bg-input);
            border-radius: 6px;
            font-size: 12px;
            margin-bottom: 6px;
            color: white;
        }

        .custom-ticker-item input {
            background: black;
            color: white;
            border: 1px solid #333;
            padding: 2px 4px;
            border-radius: 3px;
            width: 80px;
        }

        .custom-ticker-item span, .blacklist-tag span {
            flex-grow: 1;
        }
        
        .custom-ticker-item input {
            width: 80px;
            text-align: right;
            background: #0d0d0d;
            padding: 4px 8px;
        }

        .remove-btn {
            cursor: pointer;
            color: var(--text-secondary);
            font-weight: bold;
        }
        .remove-btn:hover {
            color: var(--accent-red);
        }

        /* --- Основной контент --- */
        .main-content {
            flex: 1;
            min-width: 400px;
            display: flex;
            flex-direction: column;
            padding: 10px;
            gap: 10px;
            overflow: hidden;
        }

        .main-header {
            display: flex;
            justify-content: flex-end;
            align-items: center;
            gap: 15px;
            padding: 5px 10px;
            flex-shrink: 0;
        }

        .connection-status {
            display: flex;
            align-items: center;
            gap: 8px;
            font-size: 12px;
        }

        .status-indicator {
            width: 10px;
            height: 10px;
            border-radius: 50%;
            background: var(--accent-red);
        }
        .status-indicator.connected {
            background: var(--accent-green);
            animation: pulse 2s infinite;
        }
        
        @keyframes pulse {
            0% { box-shadow: 0 0 0 0 rgba(35, 134, 54, 0.7); }
            70% { box-shadow: 0 0 0 10px rgba(35, 134, 54, 0); }
            100% { box-shadow: 0 0 0 0 rgba(35, 134, 54, 0); }
        }

        .header-btn {
            background: none;
            border: 1px solid var(--border-color);
            color: var(--text-primary);
            padding: 5px 15px;
            border-radius: 6px;
            cursor: pointer;
        }
        .header-btn:hover {
            background-color: var(--bg-panel);
        }
        
        .legend {
            display: flex;
            gap: 15px;
            font-size: 12px;
            border-left: 1px solid var(--border-color);
            padding-left: 15px;
        }
        .legend-item { display: flex; align-items: center; gap: 6px; }
        .legend-color { width: 10px; height: 10px; }
        .legend-color.short { background: var(--accent-red); }
        .legend-color.long { background: var(--accent-green); }

        .chart-area {
            flex-grow: 1;
            display: flex;
            flex-direction: column;
            background-color: var(--bg-panel);
            border: 1px solid var(--border-color);
            border-radius: 6px;
            overflow: hidden;
        }
        
        .column-headers {
            display: flex;
            border-bottom: 1px solid var(--border-color);
            flex-shrink: 0;
        }
        .header-spacer {
             width: 60px;
             flex-shrink: 0;
             border-right: 1px solid var(--border-color);
        }
        .header-item {
            flex: 1;
            padding: 8px;
            text-align: center;
            color: var(--text-secondary);
            font-weight: 600;
        }
        .header-item:not(:last-child) {
            border-right: 1px solid var(--border-color);
        }
        
        .chart-content {
            flex-grow: 1;
            display: flex;
            position: relative;
        }
        
        .deviation-axis {
            width: 60px;
            flex-shrink: 0;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            padding: 10px 0;
            border-right: 1px solid var(--border-color);
            text-align: center;
            color: var(--text-secondary);
            font-size: 12px;
        }

        .heatmap-container {
            flex-grow: 1;
            display: flex;
            position: relative;
        }
        
        .center-line {
            position: absolute;
            top: 50%;
            left: 0;
            right: 0;
            height: 1px;
            background-color: var(--border-color);
            opacity: 0.5;
            z-index: 0;
        }
        
        .density-lane {
            flex: 1;
            position: relative;
            height: 100%;
        }
        .density-lane:not(:last-child) {
            border-right: 1px solid var(--border-color);
        }

        .density-block {
            position: absolute;
            left: 5px;
            right: 5px;
            padding: 2px 5px;
            border-radius: 3px;
            font-size: 11px;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            cursor: pointer;
            transform: translateY(-50%);
            transition: top 0.3s ease, background-color 0.3s ease;
            z-index: 1;
        }
        .density-block.long {
            background-color: rgba(35, 134, 54, 0.5);
            border: 1px solid rgba(35, 134, 54, 0.8);
        }
        .density-block.short {
            background-color: rgba(218, 54, 51, 0.5);
            border: 1px solid rgba(218, 54, 51, 0.8);
        }
        .density-block:hover {
             z-index: 10;
             background-color: #3a3a3a;
             border-color: #4a4a4a;
        }

        .empty-state-message {
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            color: var(--text-secondary);
            display: none; /* Hidden by default */
        }

    </style>
</head>
<body>
    <div class="container">
        <!-- Основной контент -->
        <main class="main-content">
            <header class="main-header">
                <div class="connection-status">
                    <div class="status-indicator" id="connectionStatus"></div>
                    <span id="connectionText">Отключено</span>
                </div>
                <div class="header-controls">
                    <button class="header-btn" id="settingsBtn" style="display: none;">⚙️</button>
                    <button class="header-btn connect-btn" id="connectBtn" onclick="densityManager.connect()">Подключить</button>
                </div>
                <div class="legend">
                    <div class="legend-item"><span class="legend-color short"></span> SHORT (продажа)</div>
                    <div class="legend-item"><span class="legend-color long"></span> LONG (покупка)</div>
                </div>
            </header>
            
            <div class="chart-area">
                <div class="column-headers">
                    <div class="header-spacer"></div>
                    <div class="header-item" id="col-header-1">x1</div>
                    <div class="header-item" id="col-header-2">x2</div>
                    <div class="header-item" id="col-header-3">x3</div>
                </div>
                <div class="chart-content">
                    <div class="deviation-axis" id="deviation-axis"></div>
                    <div class="heatmap-container">
                        <div class="center-line"></div>
                        <div class="density-lane" id="lane1"></div>
                        <div class="density-lane" id="lane2"></div>
                        <div class="density-lane" id="lane3"></div>
                        <div class="empty-state-message" id="empty-state">Нет данных для отображения</div>
                    </div>
                </div>
            </div>
        </main>
        
        <!-- Панель настроек -->
        <div class="settings-panel">
            <h2 class="settings-header">Карта плотностей ордеров</h2>
            
            <div class="settings-group">
                <h3>Минимальный объём (USD)</h3>
                <div class="input-group">
                    <input type="number" id="minSize" value="10000000" step="100000">
                </div>
            </div>
            
            <div class="settings-group">
                <h3>Множители объёмов</h3>
                <div class="multiplier-inputs" style="display: flex; flex-direction: column; gap: 8px;">
                    <input type="number" id="mult1" value="2" step="0.5" min="1.1" style="width: 120px; padding: 4px 8px; background: #0d0d0d; color: white; border: 1px solid #333;">
                    <input type="number" id="mult2" value="3" step="0.5" min="1" style="width: 120px; padding: 4px 8px; background: #0d0d0d; color: white; border: 1px solid #333;">
                </div>
            </div>
            
            <div class="settings-group">
                <h3>Максимальное отклонение (%)</h3>
                <div class="input-group">
                    <input type="number" id="maxDeviation" value="10" step="1" min="1" max="10">
                </div>
            </div>
            
            <div class="settings-group">
                <h3>Минимальное время плотности (мин)</h3>
                <div class="input-group">
                    <input type="number" id="minDuration" value="1" step="1" min="1" max="60">
                </div>
            </div>
            
            <div class="settings-group">
                <h3>Блеклист тикеров</h3>
                <div class="blacklist-input-row">
                    <input type="text" id="blacklistInput" placeholder="Введите тикер...">
                    <button class="btn-add" onclick="addToBlacklist()">Добавить</button>
                </div>
                <div id="blacklistTags"></div>
            </div>
            
            <div class="settings-group">
                <h3>Индивидуальные настройки</h3>
                <div class="custom-ticker-row">
                    <input type="text" id="customTickerInput" placeholder="Тикер">
                    <input type="number" id="customSizeInput" placeholder="Объём">
                    <button class="btn-add" onclick="addCustomTicker()">+</button>
                </div>
                <div id="customTickersContainer"></div>
            </div>
        </div>
    </div>

    <script>
        class DensityManager {
            constructor() {
                this.densities = new Map(); // key -> density object
                this.settings = this.loadSettings();
                this.ws = null;
                this.reconnectAttempts = 0;
            }

            loadSettings() {
                const saved = localStorage.getItem('densitySettingsV2');
                const defaults = {
                    minSizeUsd: 10000000,
                    maxDeviation: 10,
                    minDuration: 1,
                    multipliers: [2, 3],
                    blacklist: [],
                    customTickers: [],
                    dataFormat: 'msgpack'
                };
                
                if (saved) {
                    const parsed = JSON.parse(saved);
                    return { ...defaults, ...parsed };
                }
                return defaults;
            }

            saveSettings() {
                localStorage.setItem('densitySettingsV2', JSON.stringify(this.settings));
            }

            connect() {
                if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) {
                    console.log("[WS] Already connected or connecting.");
                    return;
                }
                const format = this.settings.dataFormat || 'msgpack';
                const wsUrl = `ws://${window.location.host}/ws/densities?format=${format}`;
                this.ws = new WebSocket(wsUrl);

                this.ws.onopen = () => {
                    document.getElementById('connectionStatus').classList.add('connected');
                    document.getElementById('connectionText').textContent = 'Подключено';
                    this.reconnectAttempts = 0;
                    console.log(`[WS] Connected with ${format}`);
                };

                this.ws.onclose = () => {
                    document.getElementById('connectionStatus').classList.remove('connected');
                    document.getElementById('connectionText').textContent = 'Отключено';
                    if (this.ws) { // Avoid reconnecting after manual disconnect
                        console.log("[WS] Disconnected. Reconnecting...");
                        this.reconnect();
                    }
                };
                
                this.ws.onerror = (error) => {
                    console.error("[WS] Error:", error);
                };

                this.ws.onmessage = async (event) => {
                    try {
                        let data;
                        if (event.data instanceof Blob) {
                            const buffer = await event.data.arrayBuffer();
                            data = MessagePack.decode(new Uint8Array(buffer));
                        } else if (typeof event.data === 'string') {
                           if (event.data === 'pong') return;
                            data = JSON.parse(event.data);
                        }
                        
                        if(data) this.handleMessage(data);

                    } catch (e) {
                        console.error("Failed to parse message:", e, event.data);
                    }
                };
            }
            
            disconnect() {
                if (this.ws) {
                    const tempWs = this.ws;
                    this.ws = null; // Prevent reconnecting
                    tempWs.close();
                    document.getElementById('connectionStatus').classList.remove('connected');
                    document.getElementById('connectionText').textContent = 'Отключено';
                    console.log("[WS] Manually disconnected.");
                }
            }

            reconnect() {
                this.reconnectAttempts++;
                const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts), 30000);
                setTimeout(() => this.connect(), delay);
            }
            
            handleMessage(data) {
                if (data.type === 'snapshot') {
                    this.densities.clear();
                    data.data.forEach(item => {
                        const key = `${item.s}:${item.t}:${item.p}`;
                        this.densities.set(key, item);
                    });
                } else if (data.type === 'delta') {
                    data.data.remove?.forEach(key => this.densities.delete(key));
                    data.data.add?.forEach(item => {
                        const key = `${item.s}:${item.t}:${item.p}`;
                        this.densities.set(key, item);
                    });
                     data.data.update?.forEach(item => {
                        const key = `${item.s}:${item.t}:${item.p}`;
                        this.densities.set(key, item);
                    });
                }
                this.render();
            }

            updateUiSettings() {
                document.getElementById('minSize').value = this.settings.minSizeUsd;
                document.getElementById('maxDeviation').value = this.settings.maxDeviation;
                document.getElementById('minDuration').value = this.settings.minDuration;
                document.getElementById('mult1').value = this.settings.multipliers[0];
                document.getElementById('mult2').value = this.settings.multipliers[1];
                this.renderBlacklist();
                this.renderCustomTickers();
                this.renderDeviationAxis();
                this.updateColumnHeaders();
            }

            renderDeviationAxis() {
                const axis = document.getElementById('deviation-axis');
                const maxDev = this.settings.maxDeviation;
                axis.innerHTML = ''; // Clear previous labels

                // Create labels from +maxDev down to -maxDev
                for (let i = maxDev; i >= -maxDev; i--) {
                    const span = document.createElement('span');
                    span.textContent = `${i > 0 ? '+' : ''}${i}%`;
                    axis.appendChild(span);
                }
            }

            updateColumnHeaders() {
                const minSize = this.settings.minSizeUsd;
                const [m1, m2] = this.settings.multipliers;
                const format = (v) => v >= 1e6 ? `${(v/1e6).toFixed(1)}M` : `${(v/1e3).toFixed(0)}K`;

                const t1 = minSize * m1;
                const t2 = minSize * m2;

                document.getElementById('col-header-1').textContent = `x1 (${format(minSize)} - ${format(t1)})`;
                document.getElementById('col-header-2').textContent = `x2 (${format(t1)} - ${format(t2)})`;
                document.getElementById('col-header-3').textContent = `x3 (>${format(t2)})`;
            }

            render() {
                window.requestAnimationFrame(() => {
                    const { columns, totalCount } = this.getFilteredDensities();
                    document.getElementById('empty-state').style.display = totalCount > 0 ? 'none' : 'block';

                    for (let i = 0; i < 3; i++) {
                        this.renderLane(i + 1, columns[i]);
                    }
                });
            }
            
            getFilteredDensities() {
                const columns = [[], [], []];
                let totalCount = 0;
                
                const blacklistSet = new Set(this.settings.blacklist);
                const customTickersMap = new Map(this.settings.customTickers);

                for (const density of this.densities.values()) {
                    if (blacklistSet.has(density.s)) continue;
                    if (Math.abs(density.pct) > this.settings.maxDeviation) continue;

                    const minSize = customTickersMap.get(density.s) || this.settings.minSizeUsd;
                    if (density.u < minSize) continue;
                    
                    // Фильтрация по минимальному времени плотности (в секундах)
                    const minDurationSeconds = this.settings.minDuration * 60;
                    if (density.d < minDurationSeconds) continue;

                    totalCount++;
                    
                    const [m1, m2] = this.settings.multipliers;
                    const t1 = minSize * m1;
                    const t2 = minSize * m2;

                    if (density.u < t1) columns[0].push(density);
                    else if (density.u < t2) columns[1].push(density);
                    else columns[2].push(density);
                }
                return { columns, totalCount };
            }

            renderLane(laneNum, densities) {
                const lane = document.getElementById(`lane${laneNum}`);
                const maxDev = this.settings.maxDeviation;
                
                const existingBlocks = new Map();
                lane.querySelectorAll('.density-block').forEach(b => existingBlocks.set(b.dataset.key, b));

                for (const density of densities) {
                    const key = `${density.s}:${density.t}:${density.p}`;
                    let block = existingBlocks.get(key);

                    if (!block) {
                        block = document.createElement('div');
                        block.className = 'density-block';
                        block.dataset.key = key;
                        lane.appendChild(block);
                    }
                    
                    block.textContent = `${density.s} ${this.formatUSD(density.u)} (${this.formatDuration(density.d)})`;
                    block.title = `${density.s} | ${density.t === 'L' ? 'LONG' : 'SHORT'}\nОбъём: ${this.formatUSD(density.u)}\nЦена: ${density.p}\nОтклонение: ${density.pct.toFixed(2)}%\nДлительность: ${this.formatDuration(density.d)}`;
                    block.classList.toggle('long', density.t === 'L');
                    block.classList.toggle('short', density.t === 'S');

                    const topPercent = 50 - (density.pct / maxDev * 50);
                    block.style.top = `${topPercent}%`;
                    
                    existingBlocks.delete(key);
                }
                
                existingBlocks.forEach(block => block.remove());
            }
            
            formatUSD(value) {
                if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
                if (value >= 1_000) return `${(value / 1_000).toFixed(0)}K`;
                return value;
            }

            formatDuration(seconds) {
                if (seconds >= 3600) {
                    const hours = Math.floor(seconds / 3600);
                    const minutes = Math.floor((seconds % 3600) / 60);
                    return `${hours}ч ${minutes}м`;
                } else if (seconds >= 60) {
                    const minutes = Math.floor(seconds / 60);
                    const secs = seconds % 60;
                    return `${minutes}м ${secs}с`;
                }
                return `${seconds}с`;
            }
        }

        const densityManager = new DensityManager();

        function applySettings() {
            densityManager.settings.minSizeUsd = parseInt(document.getElementById('minSize').value);
            
            let maxDev = parseInt(document.getElementById('maxDeviation').value);
            if (maxDev > 10) {
                maxDev = 10;
                document.getElementById('maxDeviation').value = 10;
            } else if (maxDev < 1) {
                maxDev = 1;
                document.getElementById('maxDeviation').value = 1;
            }
            densityManager.settings.maxDeviation = maxDev;
            
            let minDuration = parseInt(document.getElementById('minDuration').value);
            if (minDuration > 60) {
                minDuration = 60;
                document.getElementById('minDuration').value = 60;
            } else if (minDuration < 1) {
                minDuration = 1;
                document.getElementById('minDuration').value = 1;
            }
            densityManager.settings.minDuration = minDuration;

            densityManager.settings.multipliers = [
                parseFloat(document.getElementById('mult1').value),
                parseFloat(document.getElementById('mult2').value)
            ];
            densityManager.saveSettings();
            densityManager.updateUiSettings();
            densityManager.render();
        }
        
        function addToBlacklist() {
            const input = document.getElementById('blacklistInput');
            const ticker = input.value.trim().toUpperCase();
            if (ticker && !densityManager.settings.blacklist.includes(ticker)) {
                densityManager.settings.blacklist.push(ticker);
                applySettings();
                input.value = '';
            }
        }
        function removeFromBlacklist(ticker) {
            densityManager.settings.blacklist = densityManager.settings.blacklist.filter(t => t !== ticker);
            applySettings();
        }
        function addCustomTicker() {
            const tickerInput = document.getElementById('customTickerInput');
            const sizeInput = document.getElementById('customSizeInput');
            const ticker = tickerInput.value.trim().toUpperCase();
            const size = parseInt(sizeInput.value);
            
            if (ticker && size > 0) {
                const existing = densityManager.settings.customTickers.findIndex(([t]) => t === ticker);
                if (existing !== -1) {
                    densityManager.settings.customTickers[existing][1] = size;
                } else {
                    densityManager.settings.customTickers.push([ticker, size]);
                }
                applySettings();
                tickerInput.value = '';
                sizeInput.value = '';
            }
        }
        function removeCustomTicker(ticker) {
            densityManager.settings.customTickers = densityManager.settings.customTickers.filter(([t]) => t !== ticker);
            applySettings();
        }

        densityManager.renderBlacklist = function() {
            const container = document.getElementById('blacklistTags');
            container.innerHTML = this.settings.blacklist.map(ticker => `
                <div class="blacklist-tag">
                    <span>${ticker}</span>
                    <span class="remove-btn" onclick="removeFromBlacklist('${ticker}')">×</span>
                </div>
            `).join('');
        }
        densityManager.renderCustomTickers = function() {
            const container = document.getElementById('customTickersContainer');
            container.innerHTML = this.settings.customTickers.map(([ticker, size]) => `
                <div class="custom-ticker-item">
                    <span>${ticker}</span>
                    <input type="number" value="${size}" onchange="updateCustomTickerSize('${ticker}', this.value)">
                    <span class="remove-btn" onclick="removeCustomTicker('${ticker}')">×</span>
                </div>
            `).join('');
        }
        function updateCustomTickerSize(ticker, newSize) {
             const size = parseInt(newSize);
             if (ticker && size > 0) {
                const existing = densityManager.settings.customTickers.findIndex(([t]) => t === ticker);
                if (existing !== -1) {
                    densityManager.settings.customTickers[existing][1] = size;
                    applySettings();
                }
            }
        }
        
        // --- Init ---
        document.addEventListener('DOMContentLoaded', () => {
            densityManager.updateUiSettings();

            ['minSize', 'maxDeviation', 'minDuration', 'mult1', 'mult2'].forEach(id => {
                document.getElementById(id).addEventListener('change', applySettings);
            });
            
            densityManager.connect();
        });
    </script>
</body>
</html>
    """
    return HTMLResponse(content=html)


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
    <title>🚨 Alerts Dashboard - Dark Theme</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body { 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background: #0d0d0d;
            min-height: 100vh;
            color: #e0e0e0;
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
            background: #1a1a1a;
            border: 1px solid #2a2a2a;
            border-radius: 8px;
            padding: 20px;
            height: fit-content;
        }
        
        .main-content {
            display: flex;
            flex-direction: column;
            gap: 20px;
        }
        
        .header {
            background: #1a1a1a;
            border: 1px solid #2a2a2a;
            border-radius: 8px;
            padding: 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        
        .header h1 {
            color: #ffffff;
            font-size: 24px;
            font-weight: 500;
        }
        
        .header-controls {
            display: flex;
            gap: 15px;
            align-items: center;
        }
        
        .help-btn {
            background: #2a2a2a;
            color: #e0e0e0;
            border: 1px solid #3a3a3a;
            padding: 8px 16px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 13px;
            transition: all 0.2s ease;
            display: flex;
            align-items: center;
            gap: 5px;
        }
        
        .help-btn:hover {
            background: #3a3a3a;
            border-color: #4a4a4a;
        }
        
        .status-indicator {
            padding: 6px 12px;
            border-radius: 4px;
            font-size: 13px;
            display: flex;
            align-items: center;
            gap: 8px;
            background: #2a2a2a;
            border: 1px solid #3a3a3a;
        }
        
        .status-indicator::before {
            content: '';
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: currentColor;
        }
        
        .connected { 
            color: #4CAF50;
        }
        
        .disconnected { 
            color: #f44336;
        }
        
        .section {
            background: #1a1a1a;
            border: 1px solid #2a2a2a;
            border-radius: 8px;
            padding: 20px;
        }
        
        .section h3 {
            margin-bottom: 15px;
            color: #ffffff;
            font-size: 16px;
            font-weight: 500;
        }
        
        .form-group {
            margin-bottom: 15px;
        }
        
        .form-group label {
            display: block;
            margin-bottom: 8px;
            font-size: 13px;
            color: #a0a0a0;
            font-weight: 400;
        }
        
        input {
            width: 100%;
            padding: 8px 12px;
            background: #0d0d0d;
            border: 1px solid #2a2a2a;
            border-radius: 4px;
            color: #e0e0e0;
            font-size: 13px;
            transition: all 0.2s ease;
        }
        
        input:focus {
            outline: none;
            border-color: #3a3a3a;
            background: #1a1a1a;
        }
        
        button {
            width: 100%;
            padding: 8px 16px;
            background: #2a2a2a;
            border: 1px solid #3a3a3a;
            border-radius: 4px;
            color: #e0e0e0;
            font-size: 13px;
            cursor: pointer;
            transition: all 0.2s ease;
            margin-top: 5px;
        }
        
        button:hover {
            background: #3a3a3a;
            border-color: #4a4a4a;
        }
        
        .btn-danger {
            background: rgba(244, 67, 54, 0.1);
            border-color: rgba(244, 67, 54, 0.3);
            color: #f44336;
        }
        
        .btn-danger:hover {
            background: rgba(244, 67, 54, 0.2);
            border-color: rgba(244, 67, 54, 0.5);
        }
        
        .btn-success {
            background: rgba(76, 175, 80, 0.1);
            border-color: rgba(76, 175, 80, 0.3);
            color: #4CAF50;
        }
        
        .btn-success:hover {
            background: rgba(76, 175, 80, 0.2);
            border-color: rgba(76, 175, 80, 0.5);
        }
        
        .btn-secondary {
            background: #2a2a2a;
            border-color: #3a3a3a;
            color: #a0a0a0;
        }
        
        .btn-secondary:hover {
            background: #3a3a3a;
            border-color: #4a4a4a;
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
            background: rgba(0, 0, 0, 0.9);
            backdrop-filter: blur(10px);
        }
        
        .modal-content {
            background: #1a1a1a;
            border: 1px solid #2a2a2a;
            margin: 2% auto;
            padding: 0;
            border-radius: 8px;
            width: 95%;
            max-width: 1200px;
            max-height: 90vh;
            overflow-y: auto;
            animation: modalSlideIn 0.3s ease-out;
        }
        
        @keyframes modalSlideIn {
            from {
                transform: translateY(-30px);
                opacity: 0;
            }
            to {
                transform: translateY(0);
                opacity: 1;
            }
        }
        
        .modal-header {
            background: #0d0d0d;
            border-bottom: 1px solid #2a2a2a;
            color: #ffffff;
            padding: 20px 30px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        
        .modal-header h2 {
            margin: 0;
            font-size: 20px;
            font-weight: 500;
        }
        
        .close-btn {
            background: none;
            border: none;
            color: #a0a0a0;
            font-size: 24px;
            cursor: pointer;
            width: auto;
            margin: 0;
            padding: 0;
            line-height: 1;
        }
        
        .close-btn:hover {
            color: #ffffff;
        }
        
        .modal-body {
            padding: 30px;
        }
        
        .syntax-section {
            margin-bottom: 40px;
        }

        .section-title {
            font-size: 18px;
            color: #ffffff;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 1px solid #2a2a2a;
            font-weight: 500;
        }

        .modules-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(500px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }

        .module-card {
            background: #0d0d0d;
            border: 1px solid #2a2a2a;
            border-radius: 8px;
            padding: 20px;
            transition: all 0.3s ease;
        }

        .module-card:hover {
            border-color: #3a3a3a;
        }

        .module-header-help {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 15px;
        }

        .module-name {
            font-size: 16px;
            font-weight: 500;
            color: #4CAF50;
        }

        .module-type {
            background: #2a2a2a;
            color: #a0a0a0;
            padding: 4px 10px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: 400;
        }

        .module-description {
            color: #a0a0a0;
            margin-bottom: 20px;
            line-height: 1.6;
            font-size: 13px;
        }

        .syntax-box {
            background: #0d0d0d;
            border: 1px solid #2a2a2a;
            color: #e0e0e0;
            padding: 15px;
            border-radius: 4px;
            font-family: 'SF Mono', Monaco, 'Courier New', monospace;
            font-size: 12px;
            margin: 15px 0;
            overflow-x: auto;
        }

        .syntax-title {
            color: #4CAF50;
            font-weight: 500;
            margin-bottom: 8px;
        }

        .param-table {
            width: 100%;
            border-collapse: collapse;
            margin: 15px 0;
            background: #0d0d0d;
            border: 1px solid #2a2a2a;
            border-radius: 4px;
            overflow: hidden;
        }

        .param-table th,
        .param-table td {
            padding: 10px 15px;
            text-align: left;
            border-bottom: 1px solid #2a2a2a;
        }

        .param-table th {
            background: #1a1a1a;
            color: #ffffff;
            font-weight: 500;
            font-size: 12px;
        }

        .param-table tr:last-child td {
            border-bottom: none;
        }

        .param-table tr:hover {
            background: #1a1a1a;
        }

        .param-name {
            font-weight: 500;
            color: #f44336;
            font-family: monospace;
            font-size: 12px;
        }

        .param-type {
            color: #4CAF50;
            font-style: italic;
            font-size: 12px;
        }

        .param-table td {
            font-size: 12px;
            color: #a0a0a0;
        }

        .operators-section {
            background: #0d0d0d;
            border: 1px solid #2a2a2a;
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 30px;
        }

        .operators-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
        }

        .operator-card {
            background: #1a1a1a;
            border: 1px solid #2a2a2a;
            padding: 20px;
            border-radius: 4px;
        }

        .operator-symbol {
            font-size: 24px;
            font-weight: bold;
            color: #f44336;
            margin-bottom: 10px;
        }

        .operator-card h4 {
            color: #ffffff;
            font-size: 14px;
            font-weight: 500;
            margin-bottom: 8px;
        }

        .operator-card p {
            color: #a0a0a0;
            font-size: 12px;
        }

        .operator-card small {
            display: block;
            color: #808080;
            font-size: 11px;
            margin-top: 5px;
        }

        .examples-section {
            background: #0d0d0d;
            border: 1px solid #2a2a2a;
            border-radius: 8px;
            padding: 20px;
        }

        .examples-section h3 {
            color: #ffffff;
            font-size: 14px;
            font-weight: 500;
            margin-bottom: 15px;
        }

        .example-box {
            background: #0d0d0d;
            border: 1px solid #2a2a2a;
            border-radius: 4px;
            margin: 10px 0;
            font-family: monospace;
            font-size: 12px;
            overflow: hidden;
        }

        .example-content {
            padding: 12px;
            color: #e0e0e0;
        }

        .example-comment {
            color: #606060;
            font-style: italic;
        }

        .copy-btn-modal {
            background: #2a2a2a;
            color: #a0a0a0;
            border: none;
            border-top: 1px solid #2a2a2a;
            padding: 6px 12px;
            cursor: pointer;
            font-size: 11px;
            transition: all 0.2s;
            width: 100%;
        }

        .copy-btn-modal:hover {
            background: #3a3a3a;
            color: #e0e0e0;
        }

        .warning-box {
            background: rgba(244, 67, 54, 0.1);
            border: 1px solid rgba(244, 67, 54, 0.3);
            border-left: 3px solid #f44336;
            padding: 15px;
            border-radius: 4px;
            margin: 15px 0;
            color: #e0e0e0;
        }

        .info-box {
            background: rgba(33, 150, 243, 0.1);
            border: 1px solid rgba(33, 150, 243, 0.3);
            border-left: 3px solid #2196F3;
            padding: 15px;
            border-radius: 4px;
            margin: 15px 0;
            color: #e0e0e0;
            font-size: 13px;
        }

        .info-box code {
            background: #0d0d0d;
            padding: 2px 6px;
            border-radius: 3px;
            font-family: monospace;
            color: #4CAF50;
        }

        .highlight {
            background: rgba(255, 193, 7, 0.2);
            padding: 2px 6px;
            border-radius: 3px;
            font-weight: 500;
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
        
        .alerts-grid::-webkit-scrollbar,
        .triggered-alerts::-webkit-scrollbar,
        .my-alerts-list::-webkit-scrollbar {
            width: 8px;
        }
        
        .alerts-grid::-webkit-scrollbar-track,
        .triggered-alerts::-webkit-scrollbar-track,
        .my-alerts-list::-webkit-scrollbar-track {
            background: #0d0d0d;
            border-radius: 4px;
        }
        
        .alerts-grid::-webkit-scrollbar-thumb,
        .triggered-alerts::-webkit-scrollbar-thumb,
        .my-alerts-list::-webkit-scrollbar-thumb {
            background: #3a3a3a;
            border-radius: 4px;
        }
        
        .alerts-grid::-webkit-scrollbar-thumb:hover,
        .triggered-alerts::-webkit-scrollbar-thumb:hover,
        .my-alerts-list::-webkit-scrollbar-thumb:hover {
            background: #4a4a4a;
        }
        
        .alert-card {
            background: #0d0d0d;
            border: 1px solid #2a2a2a;
            border-radius: 8px;
            padding: 20px;
            transition: all 0.3s ease;
            position: relative;
            overflow: hidden;
        }
        
        .alert-card:hover {
            border-color: #3a3a3a;
        }
        
        .alert-card.triggered {
            animation: alertTrigger 3s ease-in-out;
            border-color: #f44336;
        }
        
        @keyframes alertTrigger {
            0% { transform: scale(1); }
            10% { transform: scale(1.02); box-shadow: 0 0 20px rgba(244, 67, 54, 0.3); }
            20% { transform: scale(1); }
            30% { transform: scale(1.02); box-shadow: 0 0 20px rgba(244, 67, 54, 0.3); }
            100% { transform: scale(1); }
        }
        
        .alert-header {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            margin-bottom: 15px;
        }
        
        .alert-header h4 {
            color: #ffffff;
            font-size: 14px;
            font-weight: 500;
        }
        
        .alert-id {
            font-family: 'Courier New', monospace;
            font-size: 11px;
            color: #808080;
            background: #1a1a1a;
            padding: 4px 8px;
            border-radius: 4px;
            border: 1px solid #2a2a2a;
        }
        
        .alert-expression {
            font-family: 'Courier New', monospace;
            background: #1a1a1a;
            border: 1px solid #2a2a2a;
            padding: 12px;
            border-radius: 4px;
            font-size: 12px;
            color: #4CAF50;
            margin: 10px 0;
        }
        
        .alert-stats {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin: 10px 0;
            font-size: 12px;
            color: #808080;
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
            border-top: 1px solid #2a2a2a;
        }
        
        .blacklist-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 10px;
        }
        
        .blacklist-title {
            font-size: 12px;
            font-weight: 500;
            color: #a0a0a0;
        }
        
        .blacklist-count {
            font-size: 11px;
            color: #606060;
            background: #1a1a1a;
            padding: 2px 6px;
            border-radius: 4px;
            border: 1px solid #2a2a2a;
        }
        
        .blacklist-tags {
            display: flex;
            flex-wrap: wrap;
            gap: 5px;
            margin-bottom: 10px;
            min-height: 20px;
        }
        
        .blacklist-tag {
            background: rgba(244, 67, 54, 0.15);
            border: 1px solid rgba(244, 67, 54, 0.3);
            color: #f44336;
            padding: 3px 8px;
            border-radius: 4px;
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
            text-transform: uppercase;
            background: #0d0d0d;
            border: 1px solid #2a2a2a;
            border-radius: 4px;
            color: #e0e0e0;
        }
        
        .add-blacklist-btn {
            padding: 6px 12px;
            font-size: 12px;
            background: #2a2a2a;
            border: 1px solid #3a3a3a;
            color: #a0a0a0;
            border-radius: 4px;
            cursor: pointer;
            width: auto;
            margin: 0;
        }
        
        .add-blacklist-btn:hover {
            background: #3a3a3a;
            border-color: #4a4a4a;
            color: #e0e0e0;
        }
        
        .triggered-alert {
            background: #0d0d0d;
            border: 1px solid #2a2a2a;
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 15px;
            border-left: 3px solid #f44336;
            animation: newAlert 0.5s ease-out;
        }
        
        .triggered-alert.filtered {
            border-left-color: #ffc107;
        }
        
        @keyframes newAlert {
            0% { 
                opacity: 0; 
                transform: translateX(20px); 
            }
            100% { 
                opacity: 1; 
                transform: translateX(0); 
            }
        }
        
        .triggered-header {
            display: flex;
            align-items: center;
            gap: 10px;
            margin-bottom: 10px;
        }
        
        .triggered-header strong {
            color: #ffffff;
            font-size: 13px;
        }
        
        .triggered-time {
            font-size: 11px;
            color: #606060;
        }
        
        .triggered-tickers {
            display: flex;
            flex-wrap: wrap;
            gap: 5px;
            margin: 10px 0;
        }
        
        .ticker-badge {
            background: rgba(244, 67, 54, 0.15);
            border: 1px solid rgba(244, 67, 54, 0.3);
            color: #f44336;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: 500;
        }
        
        .ticker-badge.filtered {
            background: rgba(255, 193, 7, 0.15);
            border-color: rgba(255, 193, 7, 0.3);
            color: #ffc107;
        }
        
        .filtered-info {
            font-size: 11px;
            color: #ffc107;
            background: rgba(255, 193, 7, 0.1);
            border: 1px solid rgba(255, 193, 7, 0.2);
            padding: 5px 8px;
            border-radius: 4px;
            margin-top: 8px;
        }
        
        .examples {
            background: #0d0d0d;
            border: 1px solid #2a2a2a;
            padding: 12px;
            border-radius: 4px;
            margin: 15px 0;
            font-size: 12px;
            line-height: 1.6;
            color: #a0a0a0;
        }
        
        .examples strong {
            color: #e0e0e0;
        }
        
        .examples code {
            background: #1a1a1a;
            padding: 2px 6px;
            border-radius: 3px;
            font-family: 'Courier New', monospace;
            color: #4CAF50;
            border: 1px solid #2a2a2a;
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
            color: #606060;
            padding: 40px 20px;
            font-style: italic;
            font-size: 13px;
        }
        
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 15px;
            margin-bottom: 20px;
        }
        
        .stat-card {
            background: #0d0d0d;
            border: 1px solid #2a2a2a;
            padding: 15px;
            border-radius: 8px;
            text-align: center;
        }
        
        .stat-value {
            font-size: 24px;
            font-weight: 500;
            color: #4CAF50;
        }
        
        .stat-label {
            font-size: 11px;
            color: #808080;
            margin-top: 5px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
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
        
        /* Custom scrollbar for modal */
        .modal-content::-webkit-scrollbar {
            width: 8px;
        }
        
        .modal-content::-webkit-scrollbar-track {
            background: #0d0d0d;
            border-radius: 4px;
        }
        
        .modal-content::-webkit-scrollbar-thumb {
            background: #3a3a3a;
            border-radius: 4px;
        }
        
        .modal-content::-webkit-scrollbar-thumb:hover {
            background: #4a4a4a;
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
                                <tr>
                                    <td class="param-name">период</td>
                                    <td class="param-type">int</td>
                                    <td>Частота проверки (опционально)</td>
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
                                <tr>
                                    <td class="param-name">период</td>
                                    <td class="param-type">int</td>
                                    <td>Частота проверки (опционально)</td>
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

                        <!-- Order Num Module -->
                        <div class="module-card">
                            <div class="module-header-help">
                                <span class="module-name">order_num</span>
                                <span class="module-type">Кол-во сделок</span>
                            </div>
                            <div class="module-description">
                                Отслеживает процентное изменение количества сделок между двумя соседними временными окнами
                            </div>
                            
                            <div class="syntax-box">
                                <div class="syntax-title">Синтаксис:</div>
                                order_num &lt;оператор&gt; &lt;процент&gt; &lt;окно&gt; [период]
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
                                    <td>Порог изменения количества сделок в %</td>
                                </tr>
                                <tr>
                                    <td class="param-name">окно</td>
                                    <td class="param-type">int</td>
                                    <td>Размер окна сравнения в секундах</td>
                                </tr>
                                <tr>
                                    <td class="param-name">период</td>
                                    <td class="param-type">int</td>
                                    <td>Частота проверки (опционально, по умолчанию 60 сек)</td>
                                </tr>
                            </table>
                            
                            <div class="example-box">
                                <div class="example-content">
                                    <div>order_num > 150 900 60 <span class="example-comment">// +150% сделок за 15 минут</span></div>
                                </div>
                                <button class="copy-btn-modal" onclick="copyToClipboardModal('order_num > 150 900 60')">Copy</button>
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
                        
                        <div class="example-box">
                            <div class="example-content">
                                <div>order_num > 200 600 60 <span class="example-comment">// Количество сделок увеличилось на 200% за 10 минут</span></div>
                            </div>
                            <button class="copy-btn-modal" onclick="copyToClipboardModal('order_num > 200 600 60')">Copy</button>
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
                                <div>price > 3 300 60 & order_num > 100 300 60 <span class="example-comment">// Цена И активность сделок</span></div>
                            </div>
                            <button class="copy-btn-modal" onclick="copyToClipboardModal('price > 3 300 60 & order_num > 100 300 60')">Copy</button>
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
                        <ul style="margin-left: 20px; margin-top: 10px; list-style-type: disc;">
                            <li>Модуль <code style="background: #1a1a1a; padding: 2px 4px; border-radius: 3px;">funding</code> работает с абсолютным значением ставки (|rate|)</li>
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
                        • <code>order_num > 150 600 60</code> — +150% сделок за 10 минут<br>
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

            // Сравниваем в uppercase для корректной фильтрации
            const filteredTickers = alertData.tickers.filter(ticker => !blacklist.has(ticker.toUpperCase()));
            
            return {
                ...alertData,
                tickers: filteredTickers,
                filtered: filteredTickers.length !== alertData.tickers.length,
                originalTickers: alertData.tickers,
                filteredOutTickers: alertData.tickers.filter(ticker => blacklist.has(ticker.toUpperCase()))
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
                        ℹ️ Блеклист: ${data.filteredOutTickers.join(', ')}
                    </div>
                `;
            }

            content += `<div style="font-size: 12px; color: #606060;">ID: ${data.alert_id}</div>`;
            
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
                <div style="font-size: 12px; color: #606060;">ID: ${data.alert_id}</div>
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
                blacklistTags.innerHTML = '<span style="color: #606060; font-size: 11px;">Нет заблокированных тикеров</span>';
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
                            <div style="font-size: 11px; color: #808080; margin: 5px 0;">
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
                                    '<span style="color: #606060; font-size: 11px;">Нет заблокированных тикеров</span>' :
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
                background: ${type === 'success' ? 'rgba(76, 175, 80, 0.95)' : type === 'error' ? 'rgba(244, 67, 54, 0.95)' : 'rgba(33, 150, 243, 0.95)'};
                color: white;
                padding: 12px 20px;
                border-radius: 4px;
                box-shadow: 0 4px 15px rgba(0,0,0,0.2);
                z-index: 9999;
                max-width: 300px;
                word-wrap: break-word;
                animation: slideIn 0.3s ease-out;
                font-size: 13px;
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

from fastapi.responses import HTMLResponse

@router.get("/dashboard", response_class=HTMLResponse)
async def get_combined_dashboard() -> HTMLResponse:
    """Возвращает единый дашборд «Алерты + Карта плотностей».

    На странице два iframe:
        ├─ /demo   – панель композитных алертов
        └─ /orders – карта плотностей ордеров

    Содержимое обоих модулей остаётся неизменным, так что
    никакой дублирующей разметки, конфликтов ID и скриптов нет.
    """
    html = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <title>🚨 Алерты + 📊 Плотности</title>
    <style>
        :root {
            --bg-main: #0d0d0d;
            --border-color: #2a2a2a;
            --resizer-color: #4a4a4a;
            --resizer-hover: #6a6a6a;
        }
        * { margin:0;padding:0;box-sizing:border-box; }
        body { 
            background: var(--bg-main); 
            height:100vh; 
            overflow:hidden; 
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
        }
        .dashboard {
            display: flex;
            height: 100vh;
            position: relative;
        }
        .panel {
            height: 100%;
            overflow: hidden;
        }
        .left-panel {
            flex: 1;
            min-width: 300px;
        }
        .right-panel {
            flex: 1;
            min-width: 300px;
        }
        .resizer {
            width: 6px;
            background: var(--border-color);
            cursor: col-resize;
            position: relative;
            transition: background-color 0.2s ease;
            flex-shrink: 0;
        }
        .resizer:hover {
            background: var(--resizer-hover);
        }
        .resizer::before {
            content: '';
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            width: 2px;
            height: 30px;
            background: var(--resizer-color);
            border-radius: 1px;
        }
        .resizer:hover::before {
            background: var(--resizer-hover);
        }
        .resizer.dragging {
            background: var(--resizer-hover);
        }
        .dashboard iframe {
            width: 100%;
            height: 100%;
            border: none;
            pointer-events: auto;
        }
        .dashboard.resizing iframe {
            pointer-events: none;
        }
        
        @media (max-width: 1200px) {
            .dashboard { 
                flex-direction: column; 
            }
            .resizer {
                width: 100%;
                height: 6px;
                cursor: row-resize;
            }
            .resizer::before {
                width: 30px;
                height: 2px;
            }
            .left-panel, .right-panel {
                min-width: auto;
                min-height: 200px;
            }
        }
    </style>
</head>
<body>
    <div class="dashboard" id="dashboard">
        <div class="panel left-panel" id="leftPanel">
            <iframe src="/ws/demo" title="Composite Alerts"></iframe>
        </div>
        <div class="resizer" id="resizer"></div>
        <div class="panel right-panel" id="rightPanel">
            <iframe src="/ws/orders" title="Order Density Map"></iframe>
        </div>
    </div>

    <script>
        class DashboardResizer {
            constructor() {
                this.dashboard = document.getElementById('dashboard');
                this.leftPanel = document.getElementById('leftPanel');
                this.rightPanel = document.getElementById('rightPanel');
                this.resizer = document.getElementById('resizer');
                
                this.isResizing = false;
                this.startX = 0;
                this.startY = 0;
                this.leftStartWidth = 0;
                this.rightStartWidth = 0;
                
                this.init();
                this.loadSavedSizes();
            }

            init() {
                this.resizer.addEventListener('mousedown', this.handleMouseDown.bind(this));
                document.addEventListener('mousemove', this.handleMouseMove.bind(this));
                document.addEventListener('mouseup', this.handleMouseUp.bind(this));
                
                // Предотвращаем выделение текста при перетаскивании
                this.resizer.addEventListener('selectstart', e => e.preventDefault());
                
                // Обработка изменения размера окна
                window.addEventListener('resize', this.handleWindowResize.bind(this));
            }

            handleMouseDown(e) {
                this.isResizing = true;
                this.startX = e.clientX;
                this.startY = e.clientY;
                
                const dashboardRect = this.dashboard.getBoundingClientRect();
                const leftRect = this.leftPanel.getBoundingClientRect();
                const rightRect = this.rightPanel.getBoundingClientRect();
                
                if (window.innerWidth > 1200) {
                    // Горизонтальное изменение размера
                    this.leftStartWidth = leftRect.width;
                    this.rightStartWidth = rightRect.width;
                } else {
                    // Вертикальное изменение размера для мобильных
                    this.leftStartWidth = leftRect.height;
                    this.rightStartWidth = rightRect.height;
                }
                
                this.dashboard.classList.add('resizing');
                this.resizer.classList.add('dragging');
                document.body.style.cursor = window.innerWidth > 1200 ? 'col-resize' : 'row-resize';
                
                e.preventDefault();
            }

            handleMouseMove(e) {
                if (!this.isResizing) return;
                
                const dashboardRect = this.dashboard.getBoundingClientRect();
                
                if (window.innerWidth > 1200) {
                    // Горизонтальное изменение размера
                    const deltaX = e.clientX - this.startX;
                    const newLeftWidth = this.leftStartWidth + deltaX;
                    const newRightWidth = this.rightStartWidth - deltaX;
                    
                    const minWidth = 300;
                    const maxLeftWidth = dashboardRect.width - minWidth - 6; // 6px для resizer
                    
                    if (newLeftWidth >= minWidth && newLeftWidth <= maxLeftWidth) {
                        const leftFlex = newLeftWidth / dashboardRect.width;
                        const rightFlex = newRightWidth / dashboardRect.width;
                        
                        this.leftPanel.style.flex = `0 0 ${newLeftWidth}px`;
                        this.rightPanel.style.flex = `0 0 ${newRightWidth}px`;
                    }
                } else {
                    // Вертикальное изменение размера для мобильных
                    const deltaY = e.clientY - this.startY;
                    const newLeftHeight = this.leftStartWidth + deltaY;
                    const newRightHeight = this.rightStartWidth - deltaY;
                    
                    const minHeight = 200;
                    const maxLeftHeight = dashboardRect.height - minHeight - 6;
                    
                    if (newLeftHeight >= minHeight && newLeftHeight <= maxLeftHeight) {
                        this.leftPanel.style.flex = `0 0 ${newLeftHeight}px`;
                        this.rightPanel.style.flex = `0 0 ${newRightHeight}px`;
                    }
                }
                
                e.preventDefault();
            }

            handleMouseUp(e) {
                if (!this.isResizing) return;
                
                this.isResizing = false;
                this.dashboard.classList.remove('resizing');
                this.resizer.classList.remove('dragging');
                document.body.style.cursor = '';
                
                this.saveSizes();
            }

            handleWindowResize() {
                // Сброс размеров при изменении ориентации
                this.leftPanel.style.flex = '';
                this.rightPanel.style.flex = '';
                this.loadSavedSizes();
            }

            saveSizes() {
                const leftRect = this.leftPanel.getBoundingClientRect();
                const rightRect = this.rightPanel.getBoundingClientRect();
                const dashboardRect = this.dashboard.getBoundingClientRect();
                
                const sizes = {
                    leftRatio: window.innerWidth > 1200 
                        ? leftRect.width / dashboardRect.width 
                        : leftRect.height / dashboardRect.height,
                    rightRatio: window.innerWidth > 1200 
                        ? rightRect.width / dashboardRect.width 
                        : rightRect.height / dashboardRect.height,
                    orientation: window.innerWidth > 1200 ? 'horizontal' : 'vertical'
                };
                
                localStorage.setItem('dashboardSizes', JSON.stringify(sizes));
            }

            loadSavedSizes() {
                const saved = localStorage.getItem('dashboardSizes');
                if (!saved) return;
                
                try {
                    const sizes = JSON.parse(saved);
                    const currentOrientation = window.innerWidth > 1200 ? 'horizontal' : 'vertical';
                    
                    // Применяем сохранённые размеры только для текущей ориентации
                    if (sizes.orientation === currentOrientation) {
                        const dashboardRect = this.dashboard.getBoundingClientRect();
                        
                        if (currentOrientation === 'horizontal') {
                            const leftWidth = dashboardRect.width * sizes.leftRatio;
                            const rightWidth = dashboardRect.width * sizes.rightRatio;
                            
                            this.leftPanel.style.flex = `0 0 ${leftWidth}px`;
                            this.rightPanel.style.flex = `0 0 ${rightWidth}px`;
                        } else {
                            const leftHeight = dashboardRect.height * sizes.leftRatio;
                            const rightHeight = dashboardRect.height * sizes.rightRatio;
                            
                            this.leftPanel.style.flex = `0 0 ${leftHeight}px`;
                            this.rightPanel.style.flex = `0 0 ${rightHeight}px`;
                        }
                    }
                } catch (e) {
                    console.warn('Failed to load saved dashboard sizes:', e);
                }
            }
        }

        // Инициализация после загрузки DOM
        document.addEventListener('DOMContentLoaded', () => {
            new DashboardResizer();
        });
    </script>
</body>
</html>
    """
    return HTMLResponse(content=html)
