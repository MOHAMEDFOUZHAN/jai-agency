import sqlite3
import os

db_path = r'C:\ProgramData\jai agency\JAI_AGENCY.db'
if not os.path.exists(db_path):
    print(f"File {db_path} NOT FOUND")
else:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    print("TABLE INFO FOR sale_items:")
    print(cur.execute("PRAGMA table_info(sale_items)").fetchall())
    print("\nSAMPLE DATA FROM sale_items (last 3):")
    print(cur.execute("SELECT * FROM sale_items ORDER BY id DESC LIMIT 3").fetchall())
    print("\nSAMPLE DATA FROM products (last 3):")
    print(cur.execute("SELECT * FROM products ORDER BY code DESC LIMIT 3").fetchall())
    conn.close()
