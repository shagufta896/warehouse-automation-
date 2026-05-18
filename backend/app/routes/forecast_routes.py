"""
Forecast API routes with database integration
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.database.database import get_db
from app.ml.forecast_service import generate_forecast, get_all_products_list
from typing import Optional
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/forecast", tags=["Forecast"])


@router.get("/products")
def list_products(db: Session = Depends(get_db)):
    """Get list of all available products"""
    try:
        products = get_all_products_list(db)

        # get_all_products_list returns list of dicts — return them directly as JSON
        return {
            "total": len(products),
            "products": products
        }

    except Exception as e:
        logger.error(f"Error fetching products: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{product_name}")
def forecast_product(
    product_name: str,
    days: int = Query(default=30, ge=7, le=90, description="Number of days to forecast"),
    db: Session = Depends(get_db)
):
    """
    Generate demand forecast for a product

    - **product_name**: Name of the product (e.g., "Cold Drink")
    - **days**: Number of days to forecast (7-90 days)
    """
    try:
        # Guard against the frontend sending a literal "undefined" or empty string
        # before the user has selected a product.
        if not product_name or product_name.strip().lower() in ("undefined", "null", "none", ""):
            raise HTTPException(
                status_code=400,
                detail="product_name is required. Please select a valid product."
            )

        logger.info(f"Forecast request for {product_name}, days={days}")

        forecast_result = generate_forecast(db, product_name, days)

        return {
            "product_name": product_name,
            "forecast_days": days,
            "predictions": forecast_result['predictions'],
            "model_used": forecast_result['model_used'],
            "model_metrics": forecast_result['metrics'],
            "all_metrics": forecast_result.get('all_metrics', {}),
            "data_points": forecast_result.get('data_points', 0),
        }

    except ValueError as e:
        logger.warning(f"Validation error: {str(e)}")
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        logger.error(f"Model training failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"Forecast generation failed: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Forecast failed: {str(e)}")
