import sqlite3
conn = sqlite3.connect('inventory.db')
c = conn.cursor()
c.execute("SELECT name, sql FROM sqlite_master WHERE type='index'")
for row in c.fetchall():
    print(f"Index: {row[0]}")
    print(f"SQL: {row[1]}\n")
conn.close()
