import os
from aiogram import Bot, Dispatcher

BOT_API = os.getenv("BOT_API")
bot = Bot(token=BOT_API)
dp = Dispatcher()