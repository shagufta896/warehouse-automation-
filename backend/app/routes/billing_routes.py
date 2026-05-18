"""
Billing / Live POS desk routes
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from app.database.database import get_db
from app.database.models import Bill, BillingItem, Product, SalesHistory, StockAlert
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, date
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/billing", tags=["Billing"])


class BillingItemIn(BaseModel):
    product_id: str
    quantity: int


class BillCreate(BaseModel):
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    items: List[BillingItemIn]
    discount: float = 0.0
    gst_rate: float = 18.0
    payment_method: str = "cash"
    notes: Optional[str] = None


def _generate_bill_number(db: Session) -> str:
    """Generate a unique bill number. Queries ALL bills globally (not tenant-filtered)
    to avoid UNIQUE constraint collisions between users."""
    from sqlalchemy import text
    import random, string

    prefix = f"INV-{date.today().strftime('%Y%m%d')}-"

    # Use raw SQL to bypass the ORM tenant filter and find the true global max
    result = db.execute(
        text("SELECT bill_number FROM bills WHERE bill_number LIKE :prefix ORDER BY bill_number DESC LIMIT 1"),
        {"prefix": f"{prefix}%"}
    ).fetchone()

    if result:
        try:
            last_seq = int(result[0].split("-")[-1])
            new_seq = last_seq + 1
        except (ValueError, IndexError):
            new_seq = 1
    else:
        new_seq = 1

    bill_number = f"{prefix}{new_seq:04d}"

    # Safety: check if this exact number already exists (race condition guard)
    exists = db.execute(
        text("SELECT 1 FROM bills WHERE bill_number = :bn"),
        {"bn": bill_number}
    ).fetchone()

    if exists:
        # Fallback: append a random suffix to guarantee uniqueness
        suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=3))
        bill_number = f"{prefix}{new_seq:04d}-{suffix}"

    return bill_number


def _check_and_create_alert(db: Session, product: Product):
    uid = product.user_id
    if product.reorder_point and product.current_stock <= 0:
        existing = db.query(StockAlert).filter(
            StockAlert.user_id == uid,
            StockAlert.product_id == product.product_id,
            StockAlert.alert_type == "out_of_stock",
            StockAlert.is_read == False
        ).first()
        if not existing:
            alert = StockAlert(
                user_id=uid,
                product_id=product.product_id,
                alert_type="out_of_stock",
                message=f"{product.product_name} is out of stock."
            )
            db.add(alert)
    elif product.reorder_point and product.current_stock <= product.reorder_point:
        existing = db.query(StockAlert).filter(
            StockAlert.user_id == uid,
            StockAlert.product_id == product.product_id,
            StockAlert.alert_type == "low_stock",
            StockAlert.is_read == False
        ).first()
        if not existing:
            alert = StockAlert(
                user_id=uid,
                product_id=product.product_id,
                alert_type="low_stock",
                message=f"{product.product_name} is low on stock ({product.current_stock} units left). Reorder point: {product.reorder_point}."
            )
            db.add(alert)


@router.post("/")
def create_bill(bill_data: BillCreate, db: Session = Depends(get_db)):
    """Create a new bill and deduct inventory"""
    try:
        bill_number = _generate_bill_number(db)
        subtotal = 0.0
        items_to_create = []

        for item in bill_data.items:
            product = db.query(Product).filter(Product.product_id == item.product_id).first()
            if not product:
                raise HTTPException(status_code=404, detail=f"Product {item.product_id} not found")
            if product.current_stock < item.quantity:
                raise HTTPException(
                    status_code=400,
                    detail=f"Insufficient stock for {product.product_name}. Available: {product.current_stock}"
                )
            line_total = product.selling_price * item.quantity
            subtotal += line_total
            items_to_create.append({
                "product": product,
                "quantity": item.quantity,
                "unit_price": product.selling_price,
                "line_total": line_total,
            })

        discount_amount = subtotal * (bill_data.discount / 100)
        taxable = subtotal - discount_amount
        gst_amount = taxable * (bill_data.gst_rate / 100)
        total = taxable + gst_amount

        bill = Bill(
            bill_number=bill_number,
            customer_name=bill_data.customer_name,
            customer_phone=bill_data.customer_phone,
            subtotal=round(subtotal, 2),
            discount=round(discount_amount, 2),
            gst_rate=bill_data.gst_rate,
            gst_amount=round(gst_amount, 2),
            total=round(total, 2),
            payment_method=bill_data.payment_method,
            notes=bill_data.notes,
            status="paid"
        )
        db.add(bill)
        db.flush()

        now = datetime.utcnow()
        for item_info in items_to_create:
            product = item_info["product"]
            bi = BillingItem(
                bill_id=bill.id,
                product_id=product.product_id,
                product_name=product.product_name,
                quantity=item_info["quantity"],
                unit_price=item_info["unit_price"],
                line_total=item_info["line_total"],
            )
            db.add(bi)
            # Deduct stock
            product.current_stock = max(0, product.current_stock - item_info["quantity"])
            product.updated_at = now
            # Record sales history
            sh = SalesHistory(
                date=now,
                product_id=product.product_id,
                units_sold=item_info["quantity"],
                selling_price=item_info["unit_price"],
                day_of_week=now.strftime("%A"),
                month=now.month,
                season=_get_season(now.month),
                is_weekend=now.weekday() >= 5,
                source="billing"
            )
            db.add(sh)
            _check_and_create_alert(db, product)

        db.commit()
        db.refresh(bill)
        return {
            "id": bill.id,
            "bill_number": bill.bill_number,
            "total": bill.total,
            "status": bill.status,
            "created_at": bill.created_at.isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Bill creation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def _get_season(month: int) -> str:
    if month in [12, 1, 2]: return "Winter"
    if month in [3, 4, 5]: return "Spring"
    if month in [6, 7, 8]: return "Summer"
    return "Autumn"


@router.get("/")
def get_bills(limit: int = 50, offset: int = 0, db: Session = Depends(get_db)):
    bills = db.query(Bill).order_by(desc(Bill.created_at)).offset(offset).limit(limit).all()
    result = []
    for b in bills:
        result.append({
            "id": b.id,
            "bill_number": b.bill_number,
            "customer_name": b.customer_name,
            "total": b.total,
            "payment_method": b.payment_method,
            "status": b.status,
            "items_count": len(b.items),
            "created_at": b.created_at.isoformat()
        })
    total_count = db.query(func.count(Bill.id)).select_from(Bill).scalar()
    return {"bills": result, "total": total_count}


@router.get("/stats")
def billing_stats(db: Session = Depends(get_db)):
    today = date.today()
    today_revenue = db.query(func.sum(Bill.total)).select_from(Bill).filter(
        func.date(Bill.created_at) == today, Bill.status == "paid"
    ).scalar() or 0
    today_bills = db.query(func.count(Bill.id)).select_from(Bill).filter(
        func.date(Bill.created_at) == today
    ).scalar() or 0
    total_revenue = db.query(func.sum(Bill.total)).select_from(Bill).filter(Bill.status == "paid").scalar() or 0
    total_bills = db.query(func.count(Bill.id)).select_from(Bill).scalar() or 0
    return {
        "today_revenue": round(today_revenue, 2),
        "today_bills": today_bills,
        "total_revenue": round(total_revenue, 2),
        "total_bills": total_bills
    }


@router.get("/{bill_id}")
def get_bill(bill_id: int, db: Session = Depends(get_db)):
    bill = db.query(Bill).filter(Bill.id == bill_id).first()
    if not bill:
        raise HTTPException(status_code=404, detail="Bill not found")
    return {
        "id": bill.id,
        "bill_number": bill.bill_number,
        "customer_name": bill.customer_name,
        "customer_phone": bill.customer_phone,
        "subtotal": bill.subtotal,
        "discount": bill.discount,
        "gst_rate": bill.gst_rate,
        "gst_amount": bill.gst_amount,
        "total": bill.total,
        "payment_method": bill.payment_method,
        "status": bill.status,
        "notes": bill.notes,
        "created_at": bill.created_at.isoformat(),
        "items": [{
            "product_name": i.product_name,
            "product_id": i.product_id,
            "quantity": i.quantity,
            "unit_price": i.unit_price,
            "line_total": i.line_total
        } for i in bill.items]
    }
