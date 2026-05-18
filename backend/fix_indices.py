import sqlite3
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

db_path = 'inventory.db'

def fix_indices():
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # 1. Drop old unique indices
        logger.info("Dropping old unique indices...")
        cursor.execute("DROP INDEX IF EXISTS ix_products_product_id;")
        cursor.execute("DROP INDEX IF EXISTS ix_bills_bill_number;")
        
        # 2. Create new non-unique indices (for performance)
        logger.info("Creating non-unique indices for IDs...")
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_products_product_id ON products (product_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_bills_bill_number ON bills (bill_number);")
        
        # 3. Create new composite UNIQUE indices
        logger.info("Creating composite unique indices (multi-tenant support)...")
        cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_user_product_id ON products (user_id, product_id);")
        cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_user_bill_number ON bills (user_id, bill_number);")
        
        # 4. Also ensure other tables have user_id indices for performance
        tables = [
            'sales_history', 'forecast_results', 
            'model_metrics', 'billing_items', 
            'stock_alerts', 'manual_sales_entries'
        ]
        for table in tables:
            cursor.execute(f"CREATE INDEX IF NOT EXISTS ix_{table}_user_id ON {table} (user_id);")
            
        conn.commit()
        logger.info("Index migration successful!")
        
    except Exception as e:
        conn.rollback()
        logger.error(f"Index migration failed: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    fix_indices()
