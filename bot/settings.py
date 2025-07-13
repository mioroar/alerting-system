import os
from aiogram import Bot, Dispatcher
from dotenv import load_dotenv

load_dotenv()

BOT_API = os.getenv("BOT_API")
bot = Bot(token=BOT_API)
dp = Dispatcher()