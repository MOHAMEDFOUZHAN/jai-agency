import sqlite3
import json
import os
import datetime

import sys

def get_db_path():
    program_data = os.environ.get('ProgramData', 'C:\\ProgramData')
    jai_data_dir = os.path.join(program_data, 'jai agency')
    if not os.path.exists(jai_data_dir):
        os.makedirs(jai_data_dir, exist_ok=True)
    return os.path.join(jai_data_dir, 'JAI_AGENCY.db')

DB_FILE = get_db_path()
DATA_FILE = 'data.json'

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    # Products Table
    c.execute('''CREATE TABLE IF NOT EXISTS products (
        code TEXT PRIMARY KEY,
        name TEXT,
        category TEXT,
        price REAL,
        unit TEXT DEFAULT 'PCS',
        bizz REAL DEFAULT 0,
        gst_percent REAL DEFAULT 0,
        igst_percent REAL DEFAULT 0
    )''')

    # Suppliers Table
    c.execute('''CREATE TABLE IF NOT EXISTS suppliers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        contact TEXT,
        phone TEXT,
        email TEXT,
        balance REAL DEFAULT 0
    )''')

    # Storage (Stock) Table
    c.execute('''CREATE TABLE IF NOT EXISTS storage (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        batch_id TEXT,
        product_code TEXT,
        qty REAL,
        entry_time TEXT,
        arrival_date TEXT,
        expiry TEXT,
        cost REAL,
        invoice_no TEXT,
        FOREIGN KEY(product_code) REFERENCES products(code)
    )''')

    # Sales Log (Bills) Table
    c.execute('''CREATE TABLE IF NOT EXISTS sales_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT,
        items_count INTEGER,
        total REAL,
        payment_method TEXT,
        status TEXT DEFAULT 'ACTIVE',
        prev_total REAL DEFAULT 0
    )''')

    # Sale Items Table (Details of each bill)
    c.execute('''CREATE TABLE IF NOT EXISTS sale_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        bill_id INTEGER,
        product_code TEXT,
        product_name TEXT,
        category TEXT,
        price REAL,
        qty REAL,
        bizz REAL DEFAULT 0,
        gst_percent REAL DEFAULT 0,
        igst_percent REAL DEFAULT 0,
        FOREIGN KEY(bill_id) REFERENCES sales_log(id)
    )''')

    # Returns Log Table
    c.execute('''CREATE TABLE IF NOT EXISTS returns_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT,
        type TEXT,
        bill_id INTEGER,
        product_code TEXT,
        product_name TEXT,
        qty REAL,
        refund_amount REAL
    )''')

    conn.commit()
    conn.close()
    print("Database initialized.")

def migrate_data():
    if not os.path.exists(DATA_FILE):
        print("No data.json found. Skipping migration.")
        return

    try:
        with open(DATA_FILE, 'r') as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error reading JSON: {e}")
        return

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    # Migrate Products
    products = data.get('products', [])
    for p in products:
        c.execute('INSERT OR IGNORE INTO products (code, name, category, price, unit, bizz, gst_percent, igst_percent) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                  (p.get('code'), p.get('name'), p.get('category'), p.get('price', 0), p.get('unit', 'PCS'), p.get('bizz', 0), p.get('gst_percent', 0), p.get('igst_percent', 0)))
    
    # Migrate Suppliers
    suppliers = data.get('suppliers', [])
    for s in suppliers:
        # Check if ID exists to avoid primary key conflicts if we want to preserve IDs, 
        # but AUTOINCREMENT usually handles new ones. However, preserving old IDs is good.
        # We'll rely on insert, if ID is passed it uses it.
        c.execute('INSERT OR REPLACE INTO suppliers (id, name, contact, phone, email, balance) VALUES (?, ?, ?, ?, ?, ?)',
                  (s.get('id'), s.get('name'), s.get('contact'), s.get('phone'), s.get('email'), s.get('balance', 0)))

    # Migrate Storage
    storage = data.get('storage', [])
    for st in storage:
        c.execute('INSERT INTO storage (batch_id, product_code, qty, entry_time, arrival_date, expiry, cost, invoice_no) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                  (st.get('batch_id'), st.get('code'), st.get('qty', 0), st.get('entry_time'), st.get('arrival_date'), st.get('expiry'), st.get('cost', 0), st.get('invoice_no')))

    # Migrate Sales
    sales = data.get('sales_log', [])
    for sale in sales:
        c.execute('INSERT OR REPLACE INTO sales_log (id, date, items_count, total, payment_method, status, prev_total) VALUES (?, ?, ?, ?, ?, ?, ?)',
                  (sale.get('id'), sale.get('date'), sale.get('items', 0), sale.get('total', 0), sale.get('payment_method'), sale.get('status', 'ACTIVE'), sale.get('prev_total', 0)))
        
        # Sales Details
        details = sale.get('details', [])
        for item in details:
            # Note: item key for product code in JSON was 'id' in the JSON viewer earlier (e.g. "id": 1001), 
            # or 'code'. The POS logic suggests 'code' or 'id'.
            # I'll try to find code in 'code' or 'id'.
            p_code = item.get('code') or str(item.get('id', ''))
            
            c.execute('INSERT INTO sale_items (bill_id, product_code, product_name, category, price, qty, bizz, gst_percent, igst_percent) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
                      (sale.get('id'), p_code, item.get('name'), item.get('category', ''), item.get('price', 0), item.get('qty', 0), item.get('bizz', 0), item.get('gst_percent', 0), item.get('igst_percent', 0)))

    # Migrate Returns
    returns = data.get('returns_log', [])
    for r in returns:
        c.execute('INSERT INTO returns_log (date, type, bill_id, product_code, product_name, qty, refund_amount) VALUES (?, ?, ?, ?, ?, ?, ?)',
                  (r.get('date'), r.get('type'), r.get('bill_id'), r.get('product_code'), r.get('product_name'), r.get('qty', 0), r.get('refund_amount', 0)))

    conn.commit()
    conn.close()
    print("Migration complete.")

if __name__ == '__main__':
    init_db()
    migrate_data()
