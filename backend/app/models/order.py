from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, Numeric, Enum, Text
from sqlalchemy.orm import relationship
import enum
from app.database import Base


class PaymentStatusEnum(str, enum.Enum):
    pending = "pending"
    paid = "paid"
    failed = "failed"


class WebshopProduct(Base):
    __tablename__ = "webshop_products"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    regular_price = Column(Numeric(10, 2), nullable=False)
    member_price = Column(Numeric(10, 2), nullable=True)
    category = Column(String(100), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)

    order_items = relationship("OrderItem", back_populates="product")


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    confirmation_number = Column(String(20), unique=True, nullable=False, index=True)
    family_id = Column(Integer, ForeignKey("families.id"), nullable=True)
    customer_name = Column(String(200), nullable=False)
    customer_email = Column(String(255), nullable=False)
    is_member = Column(Boolean, default=False, nullable=False)
    total_amount = Column(Numeric(10, 2), nullable=False)
    payment_status = Column(Enum(PaymentStatusEnum), default=PaymentStatusEnum.pending, nullable=False)
    mollie_payment_id = Column(String(100), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    family = relationship("Family", back_populates="orders")
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")


class OrderItem(Base):
    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("webshop_products.id"), nullable=False)
    quantity = Column(Integer, nullable=False)
    unit_price = Column(Numeric(10, 2), nullable=False)

    order = relationship("Order", back_populates="items")
    product = relationship("WebshopProduct", back_populates="order_items")
