"""
migrate_fix_bytes.py
====================
One-time migration to fix INTEGER columns that were accidentally written as raw
bytes into the SQLite database.

Affected columns found:
  products.current_stock  — stored as little-endian 8-byte blobs
  products.reorder_point  — may also be bytes or NULL
  sales_history.units_sold
  sales_history.month

Run from the backend/ directory:
    python migrate_fix_bytes.py

Safe to run multiple times (idempotent).
"""

import sqlite3
import struct
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "inventory.db")


def decode_if_bytes(value):
    """Return an integer from either an int, None, or a little-endian bytes blob."""
    if value is None:
        return None
    if isinstance(value, (bytes, bytearray)):
        # SQLite stores up to 8-byte little-endian signed integers
        padded = value.ljust(8, b'\x00')
        return struct.unpack('<q', padded)[0]
    return int(value)


def fix_table(conn, table: str, int_columns: list[str], pk_col: str = "id"):
    cursor = conn.cursor()
    cursor.execute(f"SELECT {pk_col}, {', '.join(int_columns)} FROM {table}")
    rows = cursor.fetchall()

    fixed = 0
    for row in rows:
        pk = row[0]
        values = row[1:]
        new_values = [decode_if_bytes(v) for v in values]

        # Only update rows that actually had bytes stored
        if any(isinstance(v, (bytes, bytearray)) for v in values):
            set_clause = ", ".join(f"{col} = ?" for col in int_columns)
            cursor.execute(
                f"UPDATE {table} SET {set_clause} WHERE {pk_col} = ?",
                (*new_values, pk),
            )
            fixed += 1

    conn.commit()
    print(f"  {table}: fixed {fixed} / {len(rows)} rows")


def main():
    print(f"Opening database: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES)

    print("Fixing products table …")
    fix_table(conn, "products", ["current_stock", "reorder_point", "reorder_quantity", "supplier_lead_time"])

    print("Fixing sales_history table …")
    fix_table(conn, "sales_history", ["units_sold", "month"])

    conn.close()
    print("Migration complete.")


if __name__ == "__main__":
    main()
