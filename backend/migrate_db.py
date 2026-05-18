import sqlite3
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

db_path = 'inventory.db'

def migrate():
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # 1. Add phone column to users
        cursor.execute("PRAGMA table_info(users);")
        columns = [col[1] for col in cursor.fetchall()]
        if 'phone' not in columns:
            logger.info("Adding 'phone' column to 'users' table...")
            cursor.execute("ALTER TABLE users ADD COLUMN phone VARCHAR(20);")
        else:
            logger.info("'phone' column already exists in 'users'.")

        # 2. Check user_id in other tables
        tables_with_user_id = [
            'products', 'sales_history', 'forecast_results', 
            'model_metrics', 'bills', 'billing_items', 
            'stock_alerts', 'manual_sales_entries'
        ]
        
        for table in tables_with_user_id:
            cursor.execute(f"PRAGMA table_info({table});")
            cols = [col[1] for col in cursor.fetchall()]
            if 'user_id' not in cols:
                logger.info(f"Adding 'user_id' column to '{table}' table...")
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN user_id VARCHAR(50);")
            
        conn.commit()
        logger.info("Migration successful!")
        
    except Exception as e:
        conn.rollback()
        logger.error(f"Migration failed: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
