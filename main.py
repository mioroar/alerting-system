from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv(), override=True)

import asyncio
import uvicorn
from fastapi import FastAPI
from contextlib import suppress, asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware

from config import logger
from api.alerts import router as alerts_router
from api.ws import router as ws_router
from modules.price.price import main as price_main
from modules.volume_change.volume import main as volume_change_main
from modules.oi.oi import main as oi_main
from modules.funding.funding import main as funding_main
from bot.handlers.modules.composite import composite_loop
from db.init_db import init_db
from db.logic import close_pool


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Управляет жизненным циклом приложения."""
    background_task = asyncio.create_task(alert_processing_loop())
    await init_db()
    yield
    
    # Корректное завершение: сначала отменяем фоновые задачи
    background_task.cancel()
    try:
        await background_task
    except asyncio.CancelledError:
        pass
    
    # Затем закрываем пул соединений с БД
    await close_pool()
    logger.info("Пул соединений с БД корректно закрыт")

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

app.include_router(alerts_router, tags=["alerts"])
app.include_router(ws_router, prefix="/ws", tags=["websocket"])


async def alert_processing_loop() -> None:
    """Основной цикл обработки алертов."""
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
        logger.exception(f"Ошибка в основном цикле: {exc}")
        raise
    finally:
        for task in tasks:
            task.cancel()
        
        with suppress(asyncio.CancelledError):
            await asyncio.gather(*tasks, return_exceptions=True)


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )