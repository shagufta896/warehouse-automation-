import sqlite3
import os

db_path = 'inventory.db'
if not os.path.exists(db_path):
    print(f"Database {db_path} not found")
else:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print("Tables:")
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    print(cursor.fetchall())
    
    print("\nUsers table columns:")
    cursor.execute("PRAGMA table_info(users);")
    for col in cursor.fetchall():
        print(col)
        
    conn.close()
