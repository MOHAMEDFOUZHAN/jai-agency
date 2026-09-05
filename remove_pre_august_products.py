import sqlite3
import os
import shutil
import datetime

TARGET_DATABASES = [
    r'd:\projects\Jai Agency\datebase\JAI_AGENCY.db',
    r'C:\ProgramData\jai agency\JAI_AGENCY.db',
    r'd:\projects\Jai Agency\inventory.db'
]

CUTOFF_DATE = '2026-08-01'

def cleanup_database(db_path):
    print(f"\n" + "="*60)
    print(f"PROCESSING DATABASE: {db_path}")
    print("="*60)
    
    if not os.path.exists(db_path):
        print(f"File not found: {db_path}. Skipping.")
        return
        
    # 1. Create Timestamped Backup
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{db_path}.bak_{timestamp}"
    try:
        shutil.copy2(db_path, backup_path)
        print(f"[SUCCESS] Backup created at: {backup_path}")
    except Exception as e:
        print(f"[ERROR] Failed to create backup: {e}. Aborting cleanup for this database.")
        return

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    
    # Helper function to get row count of a table
    def get_count(table_name):
        try:
            return cur.execute(f'SELECT COUNT(*) FROM "{table_name}"').fetchone()[0]
        except Exception:
            return 0

    tables = [t[0] for t in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]

    print("\nInitial Table Counts:")
    for t in tables:
        print(f"  - {t}: {get_count(t)} rows")

    print(f"\nDeleting records prior to cutoff date: {CUTOFF_DATE}...")

    # 2. Clean storage table
    if 'storage' in tables:
        storage_before = get_count('storage')
        cur.execute('''
            DELETE FROM storage 
            WHERE (entry_time IS NOT NULL AND entry_time < ?)
               OR (arrival_date IS NOT NULL AND arrival_date < ?)
        ''', (CUTOFF_DATE, CUTOFF_DATE))
        deleted_storage = storage_before - get_count('storage')
        print(f"  - Deleted {deleted_storage} stock batch entries from 'storage'")

    # 3. Clean sales_log table
    if 'sales_log' in tables:
        sales_before = get_count('sales_log')
        cur.execute('''
            DELETE FROM sales_log 
            WHERE date IS NOT NULL AND date < ?
        ''', (CUTOFF_DATE,))
        deleted_sales = sales_before - get_count('sales_log')
        print(f"  - Deleted {deleted_sales} sales records from 'sales_log'")

    # 4. Clean orphan / pre-august sale_items
    if 'sale_items' in tables:
        items_before = get_count('sale_items')
        cur.execute('''
            DELETE FROM sale_items 
            WHERE bill_id NOT IN (SELECT id FROM sales_log)
        ''')
        deleted_items = items_before - get_count('sale_items')
        print(f"  - Deleted {deleted_items} sale line items from 'sale_items'")

    # 5. Clean returns_log, expenses, credit_payments, supplier_payments
    for tbl in ['returns_log', 'expenses', 'credit_payments', 'supplier_payments']:
        if tbl in tables:
            tbl_before = get_count(tbl)
            cur.execute(f'DELETE FROM "{tbl}" WHERE date IS NOT NULL AND date < ?', (CUTOFF_DATE,))
            deleted_tbl = tbl_before - get_count(tbl)
            print(f"  - Deleted {deleted_tbl} entries from '{tbl}'")

    # 6. Clean products table (Remove products that have no storage inventory & no sale items)
    if 'products' in tables:
        prod_before = get_count('products')
        if 'storage' in tables and 'sale_items' in tables:
            cur.execute('''
                DELETE FROM products
                WHERE code NOT IN (SELECT DISTINCT product_code FROM storage WHERE product_code IS NOT NULL)
                  AND code NOT IN (SELECT DISTINCT product_code FROM sale_items WHERE product_code IS NOT NULL)
            ''')
        elif 'storage' in tables:
            cur.execute('''
                DELETE FROM products
                WHERE code NOT IN (SELECT DISTINCT product_code FROM storage WHERE product_code IS NOT NULL)
            ''')
        deleted_prods = prod_before - get_count('products')
        print(f"  - Deleted {deleted_prods} unused products from 'products' master catalog")

    conn.commit()

    # 7. Compact / Vacuum SQLite DB
    try:
        cur.execute("VACUUM")
        print("  - Database compressed (VACUUM completed)")
    except Exception as e:
        print(f"  - VACUUM note: {e}")

    print("\nFinal Table Counts:")
    for t in tables:
        print(f"  - {t}: {get_count(t)} rows")

    conn.close()

if __name__ == "__main__":
    for db in TARGET_DATABASES:
        cleanup_database(db)
