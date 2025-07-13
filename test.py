import asyncio
from config import fetch_price_info

async def main():
    price_info = await fetch_price_info()
    print(price_info)

if __name__ == "__main__":
    asyncio.run(main())