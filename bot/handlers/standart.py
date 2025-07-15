from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

standart_router = Router()

@standart_router.message(Command("start"))
async def start_handler(message: Message):
    await message.answer("Здарова, заебал")
