import asyncio
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv(), override=True)

from bot.bot import main as bot_main
from modules.price.price import main as price_main

async def main():
    await asyncio.gather(bot_main(), price_main())

if __name__ == "__main__":
    asyncio.run(main())
