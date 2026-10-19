from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.database import Base


def utcnow():
    return datetime.now(timezone.utc)


class InventoryItem(Base):
    __tablename__ = "inventory"

    sku = Column(String(32), primary_key=True)
    name = Column(String(120), nullable=False)
    store_id = Column(String(16), nullable=False, default="WMT-BLR-001")
    on_hand = Column(Integer, nullable=False, default=0)
    reserved = Column(Integer, nullable=False, default=0)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    @property
    def available(self) -> int:
        return self.on_hand - self.reserved


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    customer_id = Column(String(32), nullable=False)
    channel = Column(String(16), nullable=False)
    status = Column(String(16), nullable=False, default="CREATED")
    total = Column(Float, nullable=False, default=0.0)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    lines = relationship("OrderLine", back_populates="order", cascade="all, delete-orphan")


class OrderLine(Base):
    __tablename__ = "order_lines"

    id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    sku = Column(String(32), nullable=False)
    quantity = Column(Integer, nullable=False)
    unit_price = Column(Float, nullable=False)
    order = relationship("Order", back_populates="lines")
