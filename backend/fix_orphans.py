import sqlite3
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

db_path = 'inventory.db'

def fix_orphans():
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Get first user ID
        cursor.execute("SELECT id FROM users LIMIT 1;")
        res = cursor.fetchone()
        if not res:
            logger.warning("No users found. Cannot fix orphans.")
            return
        
        default_user_id = res[0]
        logger.info(f"Using default user_id: {default_user_id}")
        
        tables = [
            'products', 'sales_history', 'forecast_results', 
            'model_metrics', 'bills', 'billing_items', 
            'stock_alerts', 'manual_sales_entries'
        ]
        
        for table in tables:
            cursor.execute(f"UPDATE {table} SET user_id = ? WHERE user_id IS NULL;", (default_user_id,))
            logger.info(f"Updated {cursor.rowcount} orphan rows in {table}")
            
        conn.commit()
        logger.info("Orphan cleanup successful!")
        
    except Exception as e:
        conn.rollback()
        logger.error(f"Cleanup failed: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    fix_orphans()
