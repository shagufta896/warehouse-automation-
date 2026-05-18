"""
migrate_add_inventory_constraints.py
--------------------------------------
Run once to add backup_days, storage_capacity, shelf_life_days,
supplier_pack_size columns to the existing products table.

Usage:
    cd backend
    python migrate_add_inventory_constraints.py
"""

import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "inventory.db")

NEW_COLUMNS = [
    ("backup_days",       "INTEGER"),
    ("storage_capacity",  "INTEGER"),
    ("shelf_life_days",   "INTEGER"),
    ("supplier_pack_size","INTEGER DEFAULT 1"),
]

def column_exists(cursor, table, column):
    cursor.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cursor.fetchall())

def run():
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()
    added = []
    for col_name, col_type in NEW_COLUMNS:
        if not column_exists(cur, "products", col_name):
            cur.execute(f"ALTER TABLE products ADD COLUMN {col_name} {col_type}")
            added.append(col_name)
            print(f"  + Added column: {col_name} ({col_type})")
        else:
            print(f"  - Column already exists: {col_name}")
    conn.commit()
    conn.close()
    if added:
        print(f"\nMigration complete. Added: {', '.join(added)}")
    else:
        print("\nNo changes needed - all columns already present.")

if __name__ == "__main__":
    run()
