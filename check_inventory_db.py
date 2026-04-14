import sqlite3
import os

db_path = r'd:\Jai Agency\inventory.db'
if os.path.exists(db_path):
    print(f"--- CHECKING {db_path} ---")
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    print(f"Tables: {tables}")
    if 'products' in tables:
        cols = [i[1] for i in cur.execute("PRAGMA table_info(products)").fetchall()]
        print(f"Product Columns: {cols}")
        print("Products (last 2):")
        print(cur.execute("SELECT * FROM products ORDER BY code DESC LIMIT 2").fetchall())
    conn.close()
else:
    print(f"NOT FOUND: {db_path}")
