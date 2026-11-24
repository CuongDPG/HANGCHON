"""Vận chuyển: báo phí, tạo vận đơn, in nhãn, theo dõi hành trình.

Driver: `mock` (mặc định), `ghn`, `ghtk`."""

from __future__ import annotations

import abc
from datetime import datetime

from pydantic import BaseModel, Field

from app.core.enums import Carrier, ShippingStatus


class Address(BaseModel):
    name: str
    phone: str
    address_line: str
    ward: str | None = None
    district: str | None = None
    province: str
    codes: dict[str, str] = Field(default_factory=dict, description="Mã phường/quận theo hãng (GHN...)")


class ShippingRequest(BaseModel):
    order_code: str
    to: Address
    weight_grams: int = 500
    length_cm: int | None = None
    width_cm: int | None = None
    height_cm: int | None = None
    cod_amount_vnd: int = 0
    declared_value_vnd: int = 0
    note: str | None = None
    items: list[dict] = Field(default_factory=list)


class ShippingQuote(BaseModel):
    carrier: Carrier
    service: str
    service_name: str
    fee_vnd: int
    eta_days_min: int
    eta_days_max: int


class ShipmentCreated(BaseModel):
    carrier: Carrier
    service: str
    tracking_code: str
    fee_vnd: int
    label_url: str | None = None
    expected_delivery_at: datetime | None = None
    raw: dict = Field(default_factory=dict)


class TrackingEvent(BaseModel):
    tracking_code: str
    status: ShippingStatus
    description: str
    occurred_at: datetime
    location: str | None = None


class TrackingInfo(BaseModel):
    tracking_code: str
    status: ShippingStatus
    events: list[TrackingEvent]


class ShippingDriver(abc.ABC):
    name: str

    @abc.abstractmethod
    async def quote(self, req: ShippingRequest) -> list[ShippingQuote]: ...

    @abc.abstractmethod
    async def create(self, req: ShippingRequest, service: str) -> ShipmentCreated: ...

    @abc.abstractmethod
    async def track(self, tracking_code: str) -> TrackingInfo: ...

    @abc.abstractmethod
    async def cancel(self, tracking_code: str) -> None: ...

    @abc.abstractmethod
    async def parse_webhook(self, headers: dict[str, str], body: bytes) -> list[TrackingEvent]: ...
