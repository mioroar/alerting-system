from typing import Final, TypedDict


BINANCE_FUNDING_URL: Final[str] = "https://fapi.binance.com/fapi/v1/premiumIndex"


FUNDING_CHECK_INTERVAL_SEC: Final[int] = 60          # частота опроса API
FUNDING_RETENTION_HOURS:     Final[int] = 48         # храним историю 2 суток
FIXED_LISTENER_INTERVAL_SEC: Final[int] = 60         # listener будим раз/мин



class FundingInfo(TypedDict):
    """Снимок funding‑данных одной perp‑пары."""
    symbol: str
    rate:   str
    next_funding_ts:   int
    time:   int
