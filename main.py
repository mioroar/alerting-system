import asyncio
from contextlib import suppress, asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv, find_dotenv
import uvicorn
from api.alerts import router as alerts_router
from api.ws import app as ws_app, router as ws_router
from config import logger

load_dotenv(find_dotenv(), override=True)

from modules.price.price import main as price_main
from modules.volume_change.volume import main as volume_change_main
from modules.oi.oi import main as oi_main
from modules.funding.funding import main as funding_main
from bot.handlers.modules.composite import composite_loop


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Управляет жизненным циклом приложения.
    
    Запускает background task с основным циклом обработки алертов
    при старте приложения и корректно завершает их при остановке.
    
    Args:
        app: FastAPI приложение.
        
    Yields:
        None
    """
    background_task = asyncio.create_task(alert_processing_loop())
    
    yield
    
    background_task.cancel()
    try:
        await background_task
    except asyncio.CancelledError:
        pass

app = FastAPI(
    title="Alerts API", 
    description="API для работы с алертами",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.mount("/ws", ws_app)

app.include_router(alerts_router, tags=["alerts"])
app.include_router(ws_router, tags=["demo"])


from api.ws import get_demo_page
from fastapi.responses import HTMLResponse

@app.get("/", response_class=HTMLResponse)
async def root():
    """Главная страница с демо интерфейсом"""
    return await get_demo_page()

async def alert_processing_loop() -> None:
    """
    Основной цикл обработки алертов.
    Запускает все модули системы алертинга параллельно.
    
    Запускает следующие сервисы:
    - Трекер цен криптовалют
    - Трекер изменений объема торгов
    - Трекер открытого интереса (OI)
    - Трекер ставок финансирования
    - Композитный цикл обработки алертов
    
    Returns:
        None
    """
    # Создаем задачи для всех модулей
    tasks = [
        asyncio.create_task(price_main()),
        asyncio.create_task(volume_change_main()),
        asyncio.create_task(oi_main()),
        asyncio.create_task(funding_main()),
        asyncio.create_task(composite_loop())
    ]
    
    try:
        await asyncio.gather(*tasks)
    except Exception as exc:
        logger.error(f"Ошибка в основном цикле: {exc}")
        raise
    finally:
        for task in tasks:
            task.cancel()
        
        with suppress(asyncio.CancelledError):
            await asyncio.gather(*tasks, return_exceptions=True)

async def main() -> None:
    """Запускает все основные сервисы системы алертинга одновременно.
    
    Запускает следующие сервисы параллельно:
    - FastAPI приложение с API и WebSocket
    - Трекер цен криптовалют
    - Трекер изменений объема торгов
    - Трекер открытого интереса (OI)
    - Трекер ставок финансирования
    - Композитный цикл обработки алертов
    
    Все сервисы работают асинхронно и независимо друг от друга.
    
    Returns:
        None
    """
    # Запускаем основной цикл обработки алертов
    await alert_processing_loop()

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )

