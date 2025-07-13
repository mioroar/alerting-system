from typing import TypedDict

PRICE_API_URL = "https://fapi.binance.com/fapi/v1/ticker/price"

TICKER_BLACKLIST = ["USDC"]

PRICE_CHECK_INTERVAL_IN_SECONDS = 10

class PriceInfo(TypedDict):
    symbol: str
    price: str
    time: int
