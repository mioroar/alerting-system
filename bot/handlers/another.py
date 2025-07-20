from aiogram import Router
from .modules.price import price_router
from .modules.volume import volume_router
from .modules.volume_change import volume_change_router

# Создаем главный роутер
another_router = Router()

# Включаем все модульные роутеры
another_router.include_router(price_router)
another_router.include_router(volume_router) 
another_router.include_router(volume_change_router)