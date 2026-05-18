"""
Enhanced reorder service with EOQ and dynamic safety stock
"""
from sqlalchemy.orm import Session
from app.ml.forecast_service import generate_forecast
from app.database.crud import ProductCRUD
import numpy as np
from scipy import stats
from typing import Dict
import logging

logger = logging.getLogger(__name__)


import math

def sanitize_number(value, default=0):
    if value is None:
        return default
    if math.isnan(value) or math.isinf(value):
        return default
    return max(0, value)

def _safe_int(value, default: int = 0) -> int:
    if value is None:
        return default
    if isinstance(value, (bytes, bytearray)):
        return int.from_bytes(value, byteorder='little', signed=True)
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def calculate_dynamic_safety_stock(forecast_data: list, service_level: float = 0.95) -> float:
    """
    Calculate safety stock based on demand variability
    
    Args:
        forecast_data: List of forecast predictions
        service_level: Desired service level (default 95%)
        
    Returns:
        Dynamic safety stock quantity
    """
    predicted_values = [item['yhat'] for item in forecast_data]
    demand_std = np.std(predicted_values)
    z_score = stats.norm.ppf(service_level)
    
    return round(z_score * demand_std, 2)


def calculate_eoq(annual_demand: float, ordering_cost: float = 100, holding_cost_per_unit: float = 2) -> float:
    """
    Calculate Economic Order Quantity
    
    Args:
        annual_demand: Estimated annual demand
        ordering_cost: Cost per order (default $100)
        holding_cost_per_unit: Annual holding cost per unit (default $2)
        
    Returns:
        Optimal order quantity
    """
    if annual_demand <= 0:
        return 0
    
    eoq = np.sqrt((2 * annual_demand * ordering_cost) / holding_cost_per_unit)
    return round(eoq, 2)


def calculate_reorder(
    db: Session,
    product_name: str,
    current_stock: int = None,
    lead_time: int = None,
    safety_stock: int = None,
    use_dynamic_safety_stock: bool = True,
    backup_days: int = None
) -> Dict:
    """
    Calculate comprehensive reorder recommendations
    
    Args:
        db: Database session
        product_name: Name of the product
        current_stock: Current inventory level (optional, fetched from DB if not provided)
        lead_time: Supplier lead time in days (optional, fetched from DB if not provided)
        safety_stock: Manual safety stock (optional, calculated if not provided)
        use_dynamic_safety_stock: Whether to calculate dynamic safety stock
        backup_days: Optional backup days setting
        
    Returns:
        Dictionary with reorder recommendations
    """
    import math
    try:
        # Get product from database
        product = ProductCRUD.get_product_by_name(db, product_name)
        
        if not product:
            from fastapi import HTTPException
            raise HTTPException(
                status_code=404,
                detail=f"Product '{product_name}' not found"
            )
        
        # Use database values if not provided — guard against bytes stored in SQLite
        if current_stock is None:
            current_stock = _safe_int(product.current_stock, default=0)
        else:
            current_stock = _safe_int(current_stock, default=0)

        if lead_time is None:
            lead_time = _safe_int(product.supplier_lead_time, default=5)
        else:
            lead_time = _safe_int(lead_time, default=5)
        if lead_time < 1:
            lead_time = 5

        if backup_days is None:
            if getattr(product, "backup_days", None) is not None:
                backup_days = _safe_int(product.backup_days, default=5)
            else:
                backup_days = 5
        
        shelf_life_days = _safe_int(getattr(product, "shelf_life_days", None), default=90)
        storage_capacity = _safe_int(getattr(product, "storage_capacity", None), default=0)
        supplier_pack_size = _safe_int(getattr(product, "supplier_pack_size", None), default=1)
        if supplier_pack_size < 1:
            supplier_pack_size = 1

        # [FALLBACK HANDLING]: If ML forecast fails or returns empty data, we default to the true 
        # historical daily demand to ensure the reorder calculations NEVER crash.
        # Calculate historical average for fallback
        historical_average = 0.0
        from sqlalchemy import func
        from app.database.models import SalesHistory
        from app.database.database import current_tenant_id
        try:
            tid = current_tenant_id.get()
            agg = db.query(
                func.sum(SalesHistory.units_sold).label("total"),
                func.min(SalesHistory.date).label("first_date"),
                func.max(SalesHistory.date).label("last_date"),
            ).filter(
                SalesHistory.product_id == product.product_id,
                SalesHistory.user_id == tid
            ).one()
            
            if agg.total and agg.first_date and agg.last_date:
                date_span = max((agg.last_date - agg.first_date).days, 1)
                historical_average = float(agg.total) / date_span
        except Exception as e:
            logger.warning(f"Could not calculate historical average for {product_name}: {e}")
            historical_average = 0.0

        historical_average = sanitize_number(historical_average)

        # Generate 7-day forecast for demand calculation
        forecast_result = {'metrics': {}}
        forecast_data = []
        try:
            forecast_result = generate_forecast(db, product_name, days=7)
            forecast_data = forecast_result.get('predictions', [])
            if not forecast_data:
                logger.warning(f"Empty forecast array for {product_name}. Using historical fallback.")
                predicted_values = [historical_average]
            else:
                predicted_values = [
                    max(0, float(item.get("yhat", 0)))
                    for item in forecast_data
                ]
        except Exception as e:
            logger.warning(f"Forecast generation failed for {product_name}. Using historical fallback.")
            logger.exception(e)
            predicted_values = [historical_average]
            forecast_data = []
            
        # Calculate average daily demand from forecast
        raw_avg = sum(predicted_values) / len(predicted_values) if predicted_values else historical_average
        forecast_demand = sanitize_number(raw_avg)

        # [DEMAND CAP]: Prevent ML over-prediction from inflating the suggested qty.
        # Cap forecast demand to historical average + 20% tolerance.
        # This ensures Suggested Qty reflects real sales, not model outliers.
        if historical_average > 0 and forecast_demand > historical_average * 1.2:
            logger.info(
                f"Forecast demand ({forecast_demand:.2f}) exceeds historical avg "
                f"({historical_average:.2f}) by >20% — capping to historical for reorder qty."
            )
            average_daily_demand = sanitize_number(historical_average)
        else:
            average_daily_demand = forecast_demand

        if storage_capacity <= 0:
            storage_capacity = max(10, int(round(average_daily_demand * (lead_time + backup_days * 2))))
        
        # [SAFETY STOCK LOGIC]: Safety stock acts as a buffer against demand volatility.
        # Formula: (Z-score for service level * standard deviation of demand) OR (average daily demand * backup days).
        # Calculate safety stock
        if use_dynamic_safety_stock and safety_stock is None:
            if forecast_data:
                try:
                    safety_stock = calculate_dynamic_safety_stock(forecast_data)
                except Exception as e:
                    logger.warning(f"Dynamic safety stock calculation failed for {product_name}: {e}")
                    safety_stock = average_daily_demand * backup_days
            else:
                safety_stock = average_daily_demand * backup_days
        elif safety_stock is None:
            safety_stock = average_daily_demand * backup_days

        safety_stock = sanitize_number(safety_stock)
        
        # [REORDER POINT FORMULA]: The critical threshold at which a new order must be placed.
        # Formula: (Average Daily Demand * Supplier Lead Time) + Safety Stock
        raw_reorder_point = (average_daily_demand * lead_time) + safety_stock
        reorder_point = int(round(sanitize_number(raw_reorder_point)))
        
        # Calculate days until reorder is needed
        if average_daily_demand > 0:
            raw_days = (current_stock - reorder_point) / average_daily_demand
            days_until_reorder = max(0, round(sanitize_number(raw_days, 999), 1))
        else:
            days_until_reorder = 999
            
        from datetime import datetime, timedelta
        estimated_reorder_date = (datetime.utcnow() + timedelta(days=max(0, days_until_reorder))).date()

        # Determine reorder status
        if current_stock <= 0:
            reorder_status = "Out of Stock"
        elif current_stock <= reorder_point:
            reorder_status = "Critical Reorder"
        elif current_stock <= reorder_point * 1.2:
            reorder_status = "Low Stock"
        else:
            reorder_status = "Stock Level OK"

        if product.is_reordered:
            reorder_status = "Ordered"
        
        reorder_quantity = max(0, reorder_point - current_stock)
        
        # [EOQ CALCULATIONS]: Economic Order Quantity computes the most cost-effective amount to order.
        # Formula: Square Root of [(2 * Annual Demand * Order Cost) / Holding Cost per Unit]
        annual_demand = average_daily_demand * 365
        raw_eoq = calculate_eoq(annual_demand, ordering_cost=50, holding_cost_per_unit=2)
        raw_eoq = sanitize_number(raw_eoq)
        
        cost_price = getattr(product, "cost_price", None) or 1
        holding_cost_per_unit = cost_price * 0.20
        if holding_cost_per_unit <= 0:
            holding_cost_per_unit = 1
            
        eoq = calculate_eoq(annual_demand, ordering_cost=50, holding_cost_per_unit=holding_cost_per_unit)
        eoq = sanitize_number(eoq)
        
        # Filter pipeline for suggested order quantity
        # Formula: (Daily Demand × Coverage Days) − Current Stock
        # Uses historically-capped demand so EOQ / ML spikes don't inflate the result.
        if reorder_status in ["Out of Stock", "Critical Reorder"]:
            coverage_days = lead_time + backup_days
            suggested = (average_daily_demand * coverage_days) - current_stock
            suggested = max(0, suggested)
            
            shelf_life_cap = max(0, int(round(average_daily_demand * shelf_life_days)))
            suggested = min(suggested, shelf_life_cap)
            
            storage_cap = max(0, storage_capacity - current_stock)
            suggested = min(suggested, storage_cap)
            
            final_qty = int(math.ceil(sanitize_number(suggested) / supplier_pack_size) * supplier_pack_size)
            if final_qty < 0:
                final_qty = 0
        else:
            final_qty = 0
            shelf_life_cap = max(0, int(round(average_daily_demand * shelf_life_days)))
            storage_cap = max(0, storage_capacity - current_stock)

        stock_coverage_days = round(current_stock / average_daily_demand, 1) if average_daily_demand > 0 else 0
        
        filters_applied = {
            "shelf_life_cap": shelf_life_cap,
            "storage_cap": storage_cap
        }

        result = {
            "product_name": product_name,
            "product_id": product.product_id,
            "category": product.category,
            "current_stock": current_stock,
            "average_daily_demand": round(average_daily_demand, 2),
            "lead_time": lead_time,
            "safety_stock": int(round(safety_stock)),
            "reorder_point": reorder_point,
            "reorder_quantity": reorder_quantity,
            "reorder_status": reorder_status,
            "days_until_reorder": days_until_reorder,
            "estimated_reorder_date": estimated_reorder_date.isoformat(),
            "is_reordered": product.is_reordered,
            "reordered_at": product.reordered_at.isoformat() if product.reordered_at else None,
            "raw_eoq": int(round(raw_eoq)),
            "eoq": int(round(eoq)),
            "suggested_order_quantity": final_qty,
            "stock_coverage_days": stock_coverage_days,
            "inventory_turnover_ratio": round(annual_demand / current_stock, 2) if current_stock > 0 else 0,
            "backup_days": backup_days,
            "shelf_life_days": shelf_life_days,
            "storage_capacity": storage_capacity,
            "supplier_pack_size": supplier_pack_size,
            "filters_applied": filters_applied,
            "model_metrics": forecast_result.get('metrics', {})
        }
        
        # Update product reorder parameters in database
        ProductCRUD.update_reorder_params(db, product.product_id, int(reorder_point), int(final_qty))
        
        logger.info(f"Reorder calculation completed for {product_name}")
        
        return result
        
    except Exception as e:
        logger.error(f"Reorder calculation failed for {product_name}: {str(e)}")
        raise
