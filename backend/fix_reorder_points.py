from app.database.database import SessionLocal, current_tenant_id
from app.database.models import Product, SalesHistory, StockAlert, User
from sqlalchemy import func
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def _check_and_create_alert(db, product):
    # Simplified version of the alert logic
    if product.reorder_point is not None:
        if product.current_stock <= 0:
            alert_type = "out_of_stock"
            msg = f"{product.product_name} is out of stock."
        elif product.current_stock <= product.reorder_point:
            alert_type = "low_stock"
            msg = f"{product.product_name} is low on stock ({product.current_stock} units left). Reorder point: {product.reorder_point}."
        else:
            return

        existing = db.query(StockAlert).filter(
            StockAlert.product_id == product.product_id,
            StockAlert.alert_type == alert_type,
            StockAlert.is_read == False,
            StockAlert.user_id == product.user_id
        ).first()
        
        if not existing:
            alert = StockAlert(
                user_id=product.user_id,
                product_id=product.product_id,
                alert_type=alert_type,
                message=msg
            )
            db.add(alert)

def fix_reorder_points():
    db = SessionLocal()
    try:
        users = db.query(User).all()
        for user in users:
            logger.info(f"Processing user: {user.email}")
            current_tenant_id.set(user.id)
            
            products = db.query(Product).filter(Product.user_id == user.id).all()
            for p in products:
                avg_sold = db.query(func.avg(SalesHistory.units_sold)).filter(
                    SalesHistory.product_id == p.product_id,
                    SalesHistory.user_id == user.id
                ).scalar() or 0
                
                # Formula: Daily Demand * (Lead Time + 7 days)
                lead_time = p.supplier_lead_time or 5
                p.reorder_point = int(float(avg_sold) * (lead_time + 7)) if avg_sold > 0 else max(10, lead_time + 7)
                
                logger.info(f"Updated reorder_point for {p.product_name} to {p.reorder_point}")
                
                # Re-check for alerts
                _check_and_create_alert(db, p)
            
            db.commit()
        logger.info("Reorder point update complete!")
    finally:
        db.close()

if __name__ == "__main__":
    fix_reorder_points()
