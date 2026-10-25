from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from common.db.models import Priority, ResultStatus


class TaskRequest(BaseModel):
    task_id: str
    query: str
    priority: Priority
    callback_url: str


class TaskResponse(BaseModel):
    task_id: str
    status: Literal["accepted"] = "accepted"


class ParserOffer(BaseModel):
    name: str
    price: Decimal
    url: str


class CallbackPayload(BaseModel):
    task_id: str
    status: ResultStatus
    offers: list[ParserOffer] = Field(default_factory=list)
    error: str | None = None