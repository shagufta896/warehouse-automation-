import sqlite3
conn = sqlite3.connect('inventory.db')
c = conn.cursor()
c.execute("SELECT sql FROM sqlite_master WHERE name='products'")
print("Products SQL:")
print(c.fetchone()[0])

c.execute("SELECT sql FROM sqlite_master WHERE name='bills'")
print("\nBills SQL:")
print(c.fetchone()[0])
conn.close()
