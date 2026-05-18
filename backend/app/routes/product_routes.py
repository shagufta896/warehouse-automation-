"""
Product management routes: CRUD, manual sales, alerts
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from app.database.database import get_db
from app.database.models import Product, SalesHistory, StockAlert, ManualSalesEntry
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, date
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/products", tags=["Products"])


class ProductCreate(BaseModel):
    product_id: str
    product_name: str
    category: str
    current_stock: int
    selling_price: float
    cost_price: Optional[float] = None
    supplier_lead_time: int = 5
    unit: str = "pcs"
    description: Optional[str] = None


class ProductUpdate(BaseModel):
    product_name: Optional[str] = None
    category: Optional[str] = None
    current_stock: Optional[int] = None
    selling_price: Optional[float] = None
    cost_price: Optional[float] = None
    supplier_lead_time: Optional[int] = None
    unit: Optional[str] = None
    description: Optional[str] = None
    reorder_point: Optional[int] = None


class ManualSaleIn(BaseModel):
    product_id: str
    date: str  # YYYY-MM-DD
    units_sold: int
    selling_price: Optional[float] = None
    notes: Optional[str] = None


def _get_season(month: int) -> str:
    if month in [12, 1, 2]: return "Winter"
    if month in [3, 4, 5]: return "Spring"
    if month in [6, 7, 8]: return "Summer"
    return "Autumn"


@router.get("/")
def list_products(category: Optional[str] = None, db: Session = Depends(get_db)):
    from app.database.database import current_tenant_id
    tid = current_tenant_id.get()

    q = db.query(Product).filter(Product.is_active == True, Product.user_id == tid)
    if category:
        q = q.filter(Product.category == category)
    products = q.order_by(Product.product_name).all()

    sales_aggs = db.query(
        SalesHistory.product_id,
        func.sum(SalesHistory.units_sold).label("total"),
        func.min(SalesHistory.date).label("first_date"),
        func.max(SalesHistory.date).label("last_date"),
    ).filter(SalesHistory.user_id == tid).group_by(SalesHistory.product_id).all()

    sales_map = {}
    for row in sales_aggs:
        if row.total and row.first_date and row.last_date:
            date_span = max((row.last_date - row.first_date).days, 1)
            sales_map[row.product_id] = round(float(row.total) / date_span, 1)
        else:
            sales_map[row.product_id] = 0.0

    return {"products": [{
        "product_id": p.product_id,
        "product_name": p.product_name,
        "category": p.category,
        "current_stock": p.current_stock,
        "daily_sales": sales_map.get(p.product_id, 0.0),
        "reorder_point": p.reorder_point,
        "selling_price": p.selling_price,
        "cost_price": p.cost_price,
        "supplier_lead_time": p.supplier_lead_time,
        "unit": p.unit,
        "description": p.description,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None
    } for p in products], "total": len(products)}


@router.post("/")
def create_product(data: ProductCreate, db: Session = Depends(get_db)):
    existing = db.query(Product).filter(Product.product_id == data.product_id).first()
    if existing:
        raise HTTPException(status_code=400, detail="Product ID already exists")
    product = Product(**data.dict())
    db.add(product)
    db.commit()
    db.refresh(product)
    return {"message": "Product created", "product_id": product.product_id}


@router.get("/categories")
def get_categories(db: Session = Depends(get_db)):
    cats = db.query(Product.category).distinct().filter(Product.is_active == True).all()
    return {"categories": [c[0] for c in cats if c[0]]}


@router.post("/manual-sale")
def add_manual_sale(data: ManualSaleIn, db: Session = Depends(get_db)):
    """Add a manual sales entry for sellers without CSV"""
    product = db.query(Product).filter(Product.product_id == data.product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    try:
        sale_date = datetime.strptime(data.date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
    price = data.selling_price or product.selling_price
    # Add to sales history
    sh = SalesHistory(
        date=sale_date,
        product_id=product.product_id,
        units_sold=data.units_sold,
        selling_price=price,
        day_of_week=sale_date.strftime("%A"),
        month=sale_date.month,
        season=_get_season(sale_date.month),
        is_weekend=sale_date.weekday() >= 5,
        source="manual"
    )
    db.add(sh)
    # Also keep manual entry log
    me = ManualSalesEntry(
        product_id=product.product_id,
        product_name=product.product_name,
        date=sale_date,
        units_sold=data.units_sold,
        selling_price=price,
        notes=data.notes
    )
    db.add(me)
    db.commit()
    return {"message": "Manual sale recorded", "product": product.product_name, "date": data.date}


@router.get("/manual-sales")
def get_manual_sales(product_id: Optional[str] = None, db: Session = Depends(get_db)):
    q = db.query(ManualSalesEntry)
    if product_id:
        q = q.filter(ManualSalesEntry.product_id == product_id)
    entries = q.order_by(desc(ManualSalesEntry.date)).limit(200).all()
    return {"entries": [{
        "id": e.id,
        "product_id": e.product_id,
        "product_name": e.product_name,
        "date": e.date.strftime("%Y-%m-%d"),
        "units_sold": e.units_sold,
        "selling_price": e.selling_price,
        "notes": e.notes
    } for e in entries]}


@router.get("/alerts")
def get_alerts(unread_only: bool = True, db: Session = Depends(get_db)):
    from app.database.database import current_tenant_id
    tid = current_tenant_id.get()
    q = db.query(StockAlert).filter(StockAlert.user_id == tid)
    if unread_only:
        q = q.filter(StockAlert.is_read == False)
    alerts = q.order_by(desc(StockAlert.created_at)).limit(50).all()
    return {"alerts": [{
        "id": a.id,
        "product_id": a.product_id,
        "alert_type": a.alert_type,
        "message": a.message,
        "is_read": a.is_read,
        "created_at": a.created_at.isoformat()
    } for a in alerts], "count": len(alerts)}
@router.get("/low-stock")
def get_low_stock(db: Session = Depends(get_db)):
    from app.database.database import current_tenant_id
    tid = current_tenant_id.get()
    products = db.query(Product).filter(
        Product.user_id == tid,
        Product.is_active == True,
        Product.reorder_point != None,
        Product.current_stock <= Product.reorder_point
    ).order_by(Product.current_stock).all()
    return {"products": [{
        "product_id": p.product_id,
        "product_name": p.product_name,
        "current_stock": p.current_stock,
        "reorder_point": p.reorder_point,
        "category": p.category,
        "is_out_of_stock": p.current_stock <= 0
    } for p in products], "count": len(products)}

@router.post("/alerts/{alert_id}/read")
def mark_alert_read(alert_id: int, db: Session = Depends(get_db)):
    from app.database.database import current_tenant_id
    tid = current_tenant_id.get()
    alert = db.query(StockAlert).filter(StockAlert.id == alert_id, StockAlert.user_id == tid).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    alert.is_read = True
    db.commit()
    return {"message": "Alert marked as read"}


@router.get("/dashboard/summary")
def dashboard_summary(db: Session = Depends(get_db)):
    """Summary metrics for dashboard KPI cards"""
    total_products = db.query(func.count(Product.id)).select_from(Product).filter(Product.is_active == True).scalar() or 0
    low_stock = db.query(func.count(Product.id)).select_from(Product).filter(
        Product.is_active == True,
        Product.reorder_point != None,
        Product.current_stock <= Product.reorder_point,
        Product.current_stock > 0  # Exclude out-of-stock from low-stock count
    ).scalar() or 0
    out_of_stock = db.query(func.count(Product.id)).select_from(Product).filter(
        Product.is_active == True,
        Product.current_stock <= 0
    ).scalar() or 0
    unread_alerts = db.query(func.count(StockAlert.id)).select_from(StockAlert).filter(StockAlert.is_read == False).scalar() or 0
    # Total inventory value
    products = db.query(Product).filter(Product.is_active == True).all()
    inventory_value = sum((p.current_stock or 0) * (p.selling_price or 0) for p in products)
    # Top selling (last 30 days)
    from sqlalchemy import and_
    from datetime import timedelta
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    top_products = db.query(
        SalesHistory.product_id,
        func.sum(SalesHistory.units_sold).label("total_sold")
    ).filter(SalesHistory.date >= thirty_days_ago).group_by(
        SalesHistory.product_id
    ).order_by(desc("total_sold")).limit(5).all()
    top_list = []
    for row in top_products:
        p = db.query(Product).filter(Product.product_id == row.product_id).first()
        top_list.append({
            "product_id": row.product_id,
            "product_name": p.product_name if p else row.product_id,
            "total_sold": int(row.total_sold)
        })
    # Sales last 7 days (daily)
    daily_sales = []
    for i in range(6, -1, -1):
        d = (datetime.utcnow() - timedelta(days=i)).date()
        sold = db.query(func.sum(SalesHistory.units_sold)).select_from(SalesHistory).filter(
            func.date(SalesHistory.date) == d
        ).scalar() or 0
        revenue = db.query(
            func.sum(SalesHistory.units_sold * SalesHistory.selling_price)
        ).select_from(SalesHistory).filter(func.date(SalesHistory.date) == d).scalar() or 0
        daily_sales.append({"date": str(d), "units": int(sold), "revenue": round(float(revenue), 2)})
    # Category breakdown
    cat_data = db.query(Product.category, func.count(Product.id)).filter(
        Product.is_active == True
    ).group_by(Product.category).all()
    return {
        "total_products": total_products,
        "low_stock": low_stock,
        "out_of_stock": out_of_stock,
        "unread_alerts": unread_alerts,
        "inventory_value": round(inventory_value, 2),
        "top_products": top_list,
        "daily_sales": daily_sales,
        "category_breakdown": [{"category": c, "count": n} for c, n in cat_data]
    }


# ── Parameterised routes last (must come after all static paths) ──────────────

@router.put("/{product_id}")
def update_product(product_id: str, data: ProductUpdate, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.product_id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    for field, value in data.dict(exclude_none=True).items():
        setattr(product, field, value)
    product.updated_at = datetime.utcnow()
    db.commit()
    return {"message": "Product updated"}


@router.delete("/{product_id}")
def delete_product(product_id: str, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.product_id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    product.is_active = False
    product.updated_at = datetime.utcnow()
    db.commit()
    return {"message": "Product deactivated"}
