from typing import Optional
from pydantic import BaseModel


class AlertRequest(BaseModel):
    expression: str
    user_id: str

class AlertResponse(BaseModel):
    alert_id: str
    expression: str
    subscribers_count: Optional[int] = 0
    is_websocket_connected: Optional[bool] = False