"""
CRUD operations for database models
"""
from sqlalchemy.orm import Session
from app.database.models import Product, SalesHistory, ForecastResult, ModelMetrics
from typing import List, Optional
from datetime import datetime
import pandas as pd


class ProductCRUD:
    """CRUD operations for Product model"""
    
    @staticmethod
    def create_product(db: Session, product_data: dict) -> Product:
        """Create a new product"""
        product = Product(**product_data)
        db.add(product)
        db.commit()
        db.refresh(product)
        return product
    
    @staticmethod
    def get_product_by_name(db: Session, product_name: str) -> Optional[Product]:
        """Get product by name"""
        return db.query(Product).filter(Product.product_name == product_name).first()
    
    @staticmethod
    def get_all_products(db: Session) -> List[Product]:
        """Get all products"""
        return db.query(Product).all()
    
    @staticmethod
    def update_product_stock(db: Session, product_id: str, stock: int):
        """Update product stock"""
        product = db.query(Product).filter(Product.product_id == product_id).first()
        if product:
            product.current_stock = stock
            product.updated_at = datetime.utcnow()
            db.commit()
            return product
        return None
    
    @staticmethod
    def update_reorder_params(db: Session, product_id: str, reorder_point: int, reorder_quantity: int):
        """Update reorder parameters"""
        product = db.query(Product).filter(Product.product_id == product_id).first()
        if product:
            product.reorder_point = reorder_point
            product.reorder_quantity = reorder_quantity
            product.updated_at = datetime.utcnow()
            db.commit()
            return product
        return None


class SalesHistoryCRUD:
    """CRUD operations for SalesHistory model"""
    
    @staticmethod
    def create_sales_record(db: Session, sales_data: dict) -> SalesHistory:
        """Create a sales record"""
        sales = SalesHistory(**sales_data)
        db.add(sales)
        db.commit()
        db.refresh(sales)
        return sales
    
    @staticmethod
    def bulk_create_sales(db: Session, sales_records: List[dict]):
        """Bulk insert sales records from CSV"""
        from app.database.database import current_tenant_id
        tid = current_tenant_id.get()
        if tid:
            for r in sales_records:
                r['user_id'] = tid
        db.bulk_insert_mappings(SalesHistory, sales_records)
        db.commit()
    
    @staticmethod
    def get_product_sales_history(db: Session, product_id: str) -> List[SalesHistory]:
        """Get sales history for a product"""
        return db.query(SalesHistory).filter(
            SalesHistory.product_id == product_id
        ).order_by(SalesHistory.date).all()
    
    @staticmethod
    def get_sales_dataframe(db: Session, product_name: str) -> pd.DataFrame:
        """Get sales data as pandas DataFrame for ML"""
        # Explicitly join on the string product_id FK to avoid SQLAlchemy
        # picking the wrong column (products.id integer PK vs products.product_id).
        sales = db.query(SalesHistory).join(
            Product, SalesHistory.product_id == Product.product_id
        ).filter(
            Product.product_name == product_name
        ).order_by(SalesHistory.date).all()
        
        if not sales:
            return pd.DataFrame()
        
        def _safe_int(v):
            """Decode bytes-stored integers that SQLite may return for INTEGER columns."""
            if isinstance(v, bytes):
                return int.from_bytes(v, byteorder='little', signed=True)
            return int(v) if v is not None else 0

        data = [{
            'ds': sale.date,
            'y': _safe_int(sale.units_sold),
            'day_of_week': sale.day_of_week,
            'month': _safe_int(sale.month),
            'season': sale.season,
            'is_weekend': bool(sale.is_weekend)
        } for sale in sales]
        
        return pd.DataFrame(data)


class ForecastCRUD:
    """CRUD operations for ForecastResult model"""
    
    @staticmethod
    def save_forecast(db: Session, product_id: str, forecast_data: List[dict], model_name: str):
        """Save forecast results"""
        from datetime import datetime  # ✅ Import datetime

        # Delete old forecasts
        db.query(ForecastResult).filter(ForecastResult.product_id == product_id).delete()

        # Insert new forecasts
        from app.database.database import current_tenant_id
        tid = current_tenant_id.get()
        forecasts = []
        for item in forecast_data:
            # Convert string date to datetime if needed ✅
            forecast_date = item['ds']
            if isinstance(forecast_date, str):
                forecast_date = datetime.strptime(forecast_date, '%Y-%m-%d')
            
            forecasts.append(
                ForecastResult(
                    user_id=tid,
                    product_id=product_id,
                    forecast_date=forecast_date,  # ✅ Now it's a datetime object
                    predicted_demand=item['yhat'],
                    lower_bound=item['yhat_lower'],
                    upper_bound=item['yhat_upper'],
                    model_used=model_name
                )
            )

        db.bulk_save_objects(forecasts)
        db.commit()
    
    @staticmethod
    def get_latest_forecast(db: Session, product_id: str) -> List[ForecastResult]:
        """Get latest forecast for a product"""
        return db.query(ForecastResult).filter(
            ForecastResult.product_id == product_id
        ).order_by(ForecastResult.forecast_date).all()


class ModelMetricsCRUD:
    """CRUD operations for ModelMetrics"""
    
    @staticmethod
    def save_metrics(db: Session, metrics_data: dict):
        """Save model performance metrics"""
        metrics = ModelMetrics(**metrics_data)
        db.add(metrics)
        db.commit()
        return metrics
    
    @staticmethod
    def get_latest_metrics(db: Session, product_id: str) -> Optional[ModelMetrics]:
        """Get latest metrics for a product"""
        return db.query(ModelMetrics).filter(
            ModelMetrics.product_id == product_id
        ).order_by(ModelMetrics.trained_at.desc()).first()
