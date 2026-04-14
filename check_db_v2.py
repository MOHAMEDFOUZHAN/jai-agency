import sqlite3
import os

paths = [
    r'inventory.db',
    r'JAI_AGENCY.db',
    r'C:\ProgramData\jai agency\JAI_AGENCY.db'
]

for db_path in paths:
    if os.path.exists(db_path):
        print(f"--- CHECKING {db_path} ---")
        try:
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
            print(f"Tables: {tables}")
            if 'products' in tables:
                print("Products Sample:")
                print(cur.execute("SELECT * FROM products LIMIT 2").fetchall())
            if 'sale_items' in tables:
                info = cur.execute("PRAGMA table_info(sale_items)").fetchall()
                print(f"sale_items schema: {info}")
            conn.close()
        except Exception as e:
            print(f"Error checking {db_path}: {e}")
    else:
        print(f"NOT FOUND: {db_path}")
