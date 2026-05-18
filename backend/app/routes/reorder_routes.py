"""
Reorder API routes with database integration
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database.database import get_db
from app.ml.reorder_service import calculate_reorder
from typing import Optional
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/reorder", tags=["Reorder"])


@router.get("/{product_name}")
def reorder_product(
    product_name: str,
    current_stock: Optional[int] = Query(None, ge=0, description="Current stock level"),
    lead_time: Optional[int] = Query(None, ge=1, le=30, description="Supplier lead time in days"),
    safety_stock: Optional[int] = Query(None, ge=0, description="Manual safety stock"),
    use_dynamic: bool = Query(True, description="Use dynamic safety stock calculation"),
    backup_days: Optional[int] = Query(None, description="Backup stock days"),
    db: Session = Depends(get_db)
):
    """
    Calculate reorder recommendations for a product
    
    - **product_name**: Name of the product
    - **current_stock**: Current inventory level (optional, fetched from DB if not provided)
    - **lead_time**: Supplier lead time in days (optional, fetched from DB if not provided)
    - **safety_stock**: Manual safety stock override (optional)
    - **use_dynamic**: Whether to use dynamic safety stock calculation
    - **backup_days**: Optional backup days setting
    """
    try:
        # Guard against frontend sending literal "undefined" before product is selected
        if not product_name or product_name.strip().lower() in ("undefined", "null", "none", ""):
            raise HTTPException(
                status_code=400,
                detail="product_name is required. Please select a valid product."
            )

        logger.info(f"Reorder calculation for {product_name}")
        
        reorder_data = calculate_reorder(
            db=db,
            product_name=product_name,
            current_stock=current_stock,
            lead_time=lead_time,
            safety_stock=safety_stock,
            use_dynamic_safety_stock=use_dynamic,
            backup_days=backup_days
        )
        
        return reorder_data
        
    except ValueError as e:
        logger.warning(f"Validation error: {str(e)}")
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Reorder calculation failed: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Reorder calculation failed: {str(e)}")

@router.get("/plan/all")
def get_reorder_plan(backup_days: Optional[int] = Query(5, description="Backup stock days"), db: Session = Depends(get_db)):
    """Get reorder recommendations for ALL active products"""
    from app.database.models import Product, SalesHistory
    from app.database.database import current_tenant_id
    tid = current_tenant_id.get()
    
    products = db.query(Product).filter(Product.is_active == True).all()
    results = []
    
    for p in products:
        try:
            from app.ml.reorder_service import sanitize_number
            # Use TRUE daily demand = total sold / date range span
            agg = db.query(
                func.sum(SalesHistory.units_sold).label("total"),
                func.min(SalesHistory.date).label("first_date"),
                func.max(SalesHistory.date).label("last_date"),
            ).filter(
                SalesHistory.product_id == p.product_id,
                SalesHistory.user_id == tid
            ).one()

            if agg.total and agg.first_date and agg.last_date:
                date_span = max((agg.last_date - agg.first_date).days, 1)
                true_daily_demand = sanitize_number(float(agg.total) / date_span)
            else:
                true_daily_demand = 0

            lead_time = p.supplier_lead_time or 5
            if lead_time < 1:
                lead_time = 5

            p_backup = getattr(p, "backup_days", None) if getattr(p, "backup_days", None) is not None else backup_days
            safety_stock = int(round(sanitize_number(true_daily_demand * p_backup))) if true_daily_demand > 0 else 0
            live_reorder_point = int(round(sanitize_number((true_daily_demand * lead_time) + safety_stock))) if true_daily_demand > 0 else (p.reorder_point or 0)

            days_until_reorder = 999
            if true_daily_demand > 0 and live_reorder_point:
                raw_days = (p.current_stock - live_reorder_point) / true_daily_demand
                days_until_reorder = max(0, round(sanitize_number(raw_days, 999), 1))

            from datetime import datetime, timedelta
            est_date = (datetime.utcnow() + timedelta(days=max(0, days_until_reorder))).date()

            if p.current_stock <= 0:
                reorder_status = "Out of Stock"
            elif p.current_stock <= live_reorder_point:
                reorder_status = "Critical Reorder"
            elif p.current_stock <= live_reorder_point * 1.2:
                reorder_status = "Low Stock"
            else:
                reorder_status = "Stock Level OK"

            storage_capacity = getattr(p, "storage_capacity", None)
            if not storage_capacity or storage_capacity <= 0:
                storage_capacity = max(10, int(round(sanitize_number(true_daily_demand * (lead_time + p_backup * 2))))) if true_daily_demand > 0 else 50

            results.append({
                "product_id": p.product_id,
                "product_name": p.product_name,
                "category": p.category,
                "current_stock": p.current_stock,
                "reorder_point": int(live_reorder_point),
                "storage_capacity": storage_capacity,
                "backup_days": p_backup,
                "days_until_reorder": days_until_reorder,
                "estimated_reorder_date": est_date.isoformat(),
                "is_reordered": p.is_reordered,
                "status": "Ordered" if p.is_reordered else reorder_status
            })
        except Exception as e:
            logger.error(f"Error in plan for {p.product_id}: {e}")
            continue
            
    return {"plan": results}


@router.post("/{product_id}/mark-ordered")
def mark_ordered(product_id: str, db: Session = Depends(get_db)):
    from app.database.models import Product
    from datetime import datetime
    product = db.query(Product).filter(Product.product_id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    product.is_reordered = True
    product.reordered_at = datetime.utcnow()
    db.commit()
    return {"message": f"Product {product_id} marked as ordered"}


@router.post("/{product_id}/mark-received")
def mark_received(product_id: str, db: Session = Depends(get_db)):
    from app.database.models import Product
    product = db.query(Product).filter(Product.product_id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    product.is_reordered = False
    product.reordered_at = None
    db.commit()
    return {"message": f"Product {product_id} reorder status cleared"}