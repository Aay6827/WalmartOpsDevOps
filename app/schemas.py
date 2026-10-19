from datetime import datetime
from typing import List, Literal

from pydantic import BaseModel, ConfigDict, Field

Channel = Literal["online", "store_pickup", "delivery"]
Status = Literal["CREATED", "PICKING", "PACKED", "SHIPPED", "DELIVERED", "CANCELLED"]


class InventoryUpsert(BaseModel):
    sku: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=120)
    store_id: str = "WMT-BLR-001"
    on_hand: int = Field(ge=0)


class InventoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    sku: str
    name: str
    store_id: str
    on_hand: int
    reserved: int
    available: int


class OrderLineIn(BaseModel):
    sku: str
    quantity: int = Field(gt=0)
    unit_price: float = Field(ge=0)


class OrderCreate(BaseModel):
    customer_id: str = Field(min_length=1, max_length=32)
    channel: Channel
    lines: List[OrderLineIn] = Field(min_length=1)


class OrderLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    sku: str
    quantity: int
    unit_price: float


class OrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    customer_id: str
    channel: str
    status: str
    total: float
    created_at: datetime
    lines: List[OrderLineOut]


class StatusUpdate(BaseModel):
    status: Status
