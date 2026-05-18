import sqlite3
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def migrate():
    conn = sqlite3.connect('inventory.db')
    cursor = conn.cursor()
    try:
        logger.info("Adding is_reordered column...")
        cursor.execute("ALTER TABLE products ADD COLUMN is_reordered BOOLEAN DEFAULT 0")
    except Exception as e:
        logger.warning(f"Could not add is_reordered: {e}")

    try:
        logger.info("Adding reordered_at column...")
        cursor.execute("ALTER TABLE products ADD COLUMN reordered_at DATETIME")
    except Exception as e:
        logger.warning(f"Could not add reordered_at: {e}")

    conn.commit()
    conn.close()
    logger.info("Migration finished.")

if __name__ == "__main__":
    migrate()
