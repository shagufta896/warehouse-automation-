"""
Database models for Smart Inventory Forecasting & Retail Management System
"""
from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, ForeignKey, Text
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database.database import Base
from sqlalchemy.dialects.sqlite import JSON
import uuid

class User(Base):
    __tablename__ = "users"
    id = Column(String(50), primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    full_name = Column(String(100))
    store_name = Column(String(100), nullable=True)
    email = Column(String(100), unique=True, index=True)
    phone = Column(String(20), nullable=True)
    password_hash = Column(String(200))
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    last_login = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class OTPRecord(Base):
    __tablename__ = "otp_records"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(100), index=True)
    otp_code = Column(String(10))
    purpose = Column(String(20)) # "signup", "login", "reset"
    is_used = Column(Boolean, default=False)
    expires_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(50), ForeignKey("users.id"), index=True, nullable=True)
    product_id = Column(String(50), index=True)
    product_name = Column(String(200), index=True)
    category = Column(String(100))
    current_stock = Column(Integer, default=0)
    reorder_point = Column(Integer, nullable=True)
    reorder_quantity = Column(Integer, nullable=True)
    selling_price = Column(Float)
    cost_price = Column(Float, nullable=True)
    supplier_lead_time = Column(Integer, default=5)
    unit = Column(String(50), nullable=True, default="pcs")
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    is_reordered = Column(Boolean, default=False)
    reordered_at = Column(DateTime, nullable=True)
    backup_days = Column(Integer, nullable=True, default=7)
    storage_capacity = Column(Integer, nullable=True)
    shelf_life_days = Column(Integer, nullable=True)
    supplier_pack_size = Column(Integer, default=1)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    from sqlalchemy import UniqueConstraint
    __table_args__ = (UniqueConstraint('user_id', 'product_id', name='_user_product_uc'),)
    sales_history = relationship("SalesHistory", back_populates="product")
    forecasts = relationship("ForecastResult", back_populates="product")
    billing_items = relationship("BillingItem", back_populates="product")
    alerts = relationship("StockAlert", back_populates="product")


class SalesHistory(Base):
    __tablename__ = "sales_history"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(50), ForeignKey("users.id"), index=True, nullable=True)
    date = Column(DateTime, index=True)
    product_id = Column(String(50), ForeignKey("products.product_id"))
    units_sold = Column(Integer)
    selling_price = Column(Float)
    day_of_week = Column(String(20))
    month = Column(Integer)
    season = Column(String(20))
    festival = Column(String(50), nullable=True)
    is_weekend = Column(Boolean, default=False)
    source = Column(String(50), default="csv")
    product = relationship("Product", back_populates="sales_history")


class ForecastResult(Base):
    __tablename__ = "forecast_results"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(50), ForeignKey("users.id"), index=True, nullable=True)
    product_id = Column(String(50), ForeignKey("products.product_id"))
    forecast_date = Column(DateTime)
    predicted_demand = Column(Float)
    lower_bound = Column(Float)
    upper_bound = Column(Float)
    model_used = Column(String(50))
    created_at = Column(DateTime, default=datetime.utcnow)
    product = relationship("Product", back_populates="forecasts")


class ModelMetrics(Base):
    __tablename__ = "model_metrics"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(50), ForeignKey("users.id"), index=True, nullable=True)
    product_id = Column(String(50))
    model_name = Column(String(50))
    mae = Column(Float)
    rmse = Column(Float)
    mape = Column(Float)
    trained_at = Column(DateTime, default=datetime.utcnow)
    training_samples = Column(Integer)





class Bill(Base):
    __tablename__ = "bills"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(50), ForeignKey("users.id"), index=True, nullable=True)
    bill_number = Column(String(50), index=True)

    customer_name = Column(String(200), nullable=True)
    customer_phone = Column(String(20), nullable=True)
    subtotal = Column(Float, default=0.0)
    discount = Column(Float, default=0.0)
    gst_rate = Column(Float, default=18.0)
    gst_amount = Column(Float, default=0.0)
    total = Column(Float, default=0.0)
    payment_method = Column(String(50), default="cash")
    status = Column(String(30), default="paid")
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    items = relationship("BillingItem", back_populates="bill", cascade="all, delete-orphan")

    from sqlalchemy import UniqueConstraint
    __table_args__ = (UniqueConstraint('user_id', 'bill_number', name='_user_bill_uc'),)


class BillingItem(Base):
    __tablename__ = "billing_items"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(50), ForeignKey("users.id"), index=True, nullable=True)
    bill_id = Column(Integer, ForeignKey("bills.id"))
    product_id = Column(String(50), ForeignKey("products.product_id"))
    product_name = Column(String(200))
    quantity = Column(Integer)
    unit_price = Column(Float)
    line_total = Column(Float)
    bill = relationship("Bill", back_populates="items")
    product = relationship("Product", back_populates="billing_items")


class StockAlert(Base):
    __tablename__ = "stock_alerts"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(50), ForeignKey("users.id"), index=True, nullable=True)
    product_id = Column(String(50), ForeignKey("products.product_id"))
    alert_type = Column(String(50))
    message = Column(Text)
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    product = relationship("Product", back_populates="alerts")


class ManualSalesEntry(Base):
    __tablename__ = "manual_sales_entries"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(50), ForeignKey("users.id"), index=True, nullable=True)
    product_id = Column(String(50))
    product_name = Column(String(200))
    date = Column(DateTime, index=True)
    units_sold = Column(Integer)
    selling_price = Column(Float)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
