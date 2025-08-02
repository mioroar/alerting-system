from pydantic import BaseModel


class AlertRequest(BaseModel):
    expression: str
    user_id: str

class AlertResponse(BaseModel):
    alert_id: str
    expression: str
    readable_expression: str