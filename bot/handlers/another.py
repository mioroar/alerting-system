from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

another_router = Router()

@another_router.message(Command("another"))
async def another_handler(message: Message):
    await message.answer("Another command")