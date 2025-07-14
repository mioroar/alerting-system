import asyncio
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv(), override=True)

from bot.bot import main as bot_main
from db.init_db import init_db


async def main():
    await init_db()
    await bot_main()

if __name__ == "__main__":
    asyncio.run(main())
