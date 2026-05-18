import sqlite3

db_path = 'inventory.db'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Tables to check
tables = ['users', 'products', 'sales_history', 'bills']

for table in tables:
    print(f"\n{table.upper()} table columns:")
    cursor.execute(f"PRAGMA table_info({table});")
    for col in cursor.fetchall():
        print(col)

conn.close()
