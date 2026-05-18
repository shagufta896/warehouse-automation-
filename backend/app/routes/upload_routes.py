"""
File upload routes with validation and database integration
"""
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database.database import get_db
from app.database.models import (
    Product, SalesHistory, ForecastResult,
    ModelMetrics, StockAlert, ManualSalesEntry
)
from config import settings
import pandas as pd
import io
import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/upload", tags=["Upload"])

UPLOAD_FOLDER = settings.UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


@router.post("/")
async def upload_csv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """
    Upload CSV file with inventory data.
    ALWAYS does a full replace — clears all existing inventory data first,
    then imports from the new CSV. This guarantees a clean slate on every upload.

    Expected CSV columns:
    - Date, Product_ID, Product_Name, Category, Units_Sold, Selling_Price,
      Current_Stock, Supplier_Lead_Time, Day_Of_Week, Month, Season, Festival, Weekend
    """
    try:
        # Validate file type
        if not file.filename.endswith('.csv'):
            raise HTTPException(status_code=400, detail="Only CSV files are allowed")

        # Read file content
        contents = await file.read()

        # Validate file size
        if len(contents) > settings.MAX_FILE_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"File too large. Max size: {settings.MAX_FILE_SIZE / 1024 / 1024}MB"
            )

        # Parse CSV
        try:
            df = pd.read_csv(io.BytesIO(contents))
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid CSV format: {str(e)}")

        # Validate required columns
        required_columns = ["Date", "Product_ID", "Product_Name", "Category", "Units_Sold",
                            "Selling_Price", "Current_Stock", "Supplier_Lead_Time"]

        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            raise HTTPException(
                status_code=400,
                detail=f"Missing required columns: {', '.join(missing_columns)}"
            )

        # Convert date column — handle both ISO (YYYY-MM-DD) and DD-MM-YYYY formats
        try:
            df["Date"] = pd.to_datetime(df["Date"], format="ISO8601")
        except Exception:
            try:
                df["Date"] = pd.to_datetime(df["Date"], dayfirst=True, format="mixed")
            except Exception as date_err:
                raise HTTPException(
                    status_code=400,
                    detail=f"Could not parse Date column. Expected YYYY-MM-DD or DD-MM-YYYY. Error: {date_err}"
                )

        # Normalise Product_ID to string so "P001" and 1 don't clash
        df['Product_ID'] = df['Product_ID'].astype(str)

        # Save file to uploads folder
        file_path = os.path.join(UPLOAD_FOLDER, file.filename)
        with open(file_path, "wb") as f:
            f.write(contents)

        logger.info(f"CSV file saved: {file_path}")

        # ── FULL REPLACE: wipe all existing inventory data for THIS USER first ──────────────
        from app.database.database import current_tenant_id
        tid = current_tenant_id.get()
        
        db.query(ForecastResult).filter(ForecastResult.user_id == tid).delete(synchronize_session=False)
        db.query(ModelMetrics).filter(ModelMetrics.user_id == tid).delete(synchronize_session=False)
        db.query(StockAlert).filter(StockAlert.user_id == tid).delete(synchronize_session=False)
        db.query(ManualSalesEntry).filter(ManualSalesEntry.user_id == tid).delete(synchronize_session=False)
        db.query(SalesHistory).filter(SalesHistory.user_id == tid).delete(synchronize_session=False)
        db.query(Product).filter(Product.user_id == tid).delete(synchronize_session=False)
        db.commit()
        logger.info(f"Cleared existing inventory data for user {tid}")
        # ──────────────────────────────────────────────────────────────────────
        # ──────────────────────────────────────────────────────────────────────

        products_added = 0
        sales_added = 0

        # Insert products fresh
        unique_products = df[['Product_ID', 'Product_Name', 'Category', 'Selling_Price']].drop_duplicates('Product_ID')

        for _, row in unique_products.iterrows():
            product_id = str(row['Product_ID'])
            product_rows = df[df['Product_ID'] == product_id]
            latest_row = product_rows.iloc[-1]

            product = Product(
                user_id=tid,
                product_id=product_id,
                product_name=str(row['Product_Name']),
                category=str(row['Category']),
                current_stock=int(latest_row['Current_Stock']),
                selling_price=float(row['Selling_Price']),
                supplier_lead_time=int(latest_row['Supplier_Lead_Time'])
            )
            db.add(product)
            products_added += 1

        db.commit()

        # Insert all sales history fresh
        new_sales = []
        for _, row in df.iterrows():
            product_id = str(row['Product_ID'])
            festival_val = row.get('Festival', None)
            new_sales.append(SalesHistory(
                user_id=tid,
                date=row['Date'].to_pydatetime(),
                product_id=product_id,
                units_sold=int(row['Units_Sold']),
                selling_price=float(row['Selling_Price']),
                day_of_week=str(row.get('Day_Of_Week', '')),
                month=int(row.get('Month', row['Date'].month)),
                season=str(row.get('Season', '')),
                festival=str(festival_val) if festival_val and str(festival_val).lower() not in ('nan', 'none', '') else None,
                is_weekend=bool(row.get('Weekend', 'No') == 'Yes')
            ))
            sales_added += 1

        if new_sales:
            db.add_all(new_sales)
        db.commit()
        logger.info(f"Fresh import complete: {products_added} products, {sales_added} sales records")

        # ── AUTO-CALCULATE REORDER POINTS AND GENERATE ALERTS ─────────────────
        # This ensures the dashboard and alerts page show correct data immediately.
        try:
            from app.routes.billing_routes import _check_and_create_alert
            all_products = db.query(Product).filter(Product.user_id == tid).all()
            for p in all_products:
                # Calculate average daily sales from the just-imported sales history
                # Use TRUE daily demand = total sold / date range span
                # (not naive AVG which inflates by 2-3x when products aren't sold every day)
                from sqlalchemy import func as sqlfunc
                agg = db.query(
                    sqlfunc.sum(SalesHistory.units_sold).label("total"),
                    sqlfunc.min(SalesHistory.date).label("first_date"),
                    sqlfunc.max(SalesHistory.date).label("last_date"),
                ).filter(
                    SalesHistory.product_id == p.product_id,
                    SalesHistory.user_id == tid
                ).one()

                if agg.total and agg.first_date and agg.last_date:
                    date_span = max((agg.last_date - agg.first_date).days, 1)
                    true_daily_demand = float(agg.total) / date_span
                else:
                    true_daily_demand = 0

                # Reorder point: True Daily Demand * (Lead Time + 5 days buffer)
                lead_time = p.supplier_lead_time or 5
                p.reorder_point = int(true_daily_demand * (lead_time + 5)) if true_daily_demand > 0 else max(10, lead_time + 5)
                
                # Now generate an alert if it's already low
                _check_and_create_alert(db, p)
            
            db.commit()
            logger.info(f"Calculated reorder points and generated alerts for {len(all_products)} products")
        except Exception as alert_err:
            logger.error(f"Failed to generate initial alerts: {alert_err}")
            # Don't fail the whole upload if just alerts fail
        # ──────────────────────────────────────────────────────────────────────

        return {
            "message": "File uploaded and data imported successfully",
            "file_name": file.filename,
            "saved_path": file_path,
            "total_rows": len(df),
            "products_added": products_added,
            "sales_records_added": sales_added,
            "date_range": {
                "start": df['Date'].min().strftime("%Y-%m-%d"),
                "end": df['Date'].max().strftime("%Y-%m-%d")
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Upload failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@router.delete("/reset")
def reset_inventory(db: Session = Depends(get_db)):
    """
    Manually wipe all inventory data without uploading a new CSV.
    Useful for a clean start. Billing history and user accounts are kept.
    """
    try:
        from app.database.database import current_tenant_id
        tid = current_tenant_id.get()
        
        db.query(ForecastResult).filter(ForecastResult.user_id == tid).delete(synchronize_session=False)
        db.query(ModelMetrics).filter(ModelMetrics.user_id == tid).delete(synchronize_session=False)
        db.query(StockAlert).filter(StockAlert.user_id == tid).delete(synchronize_session=False)
        db.query(ManualSalesEntry).filter(ManualSalesEntry.user_id == tid).delete(synchronize_session=False)
        db.query(SalesHistory).filter(SalesHistory.user_id == tid).delete(synchronize_session=False)
        db.query(Product).filter(Product.user_id == tid).delete(synchronize_session=False)
        db.commit()
        logger.info(f"Inventory reset for user {tid}")
        return {"message": "Your inventory data has been cleared."}
    except Exception as e:
        logger.error(f"Reset failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Reset failed: {str(e)}")


@router.get("/status")
def upload_status():
    """Get upload folder status"""
    files = [f for f in os.listdir(UPLOAD_FOLDER) if f.endswith('.csv')]

    return {
        "upload_folder": UPLOAD_FOLDER,
        "files_count": len(files),
        "files": files
    }
