import json
import os
import sys
import threading
import webbrowser
import sqlite3
import datetime
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import mailer

try:
    import webview
    from waitress import serve
except ImportError:
    # They will be needed for the EXE, but we handle missing imports for dev
    pass

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    base_path = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)

app = Flask(__name__, 
            template_folder=resource_path('templates'),
            static_folder=resource_path('static'))
app.secret_key = 'super_secret_demo_key'

@app.context_processor
def inject_now():
    return {'now': datetime.datetime.now()}

def get_db_path():
    # 1. Target ProgramData path (Recommended for shared application data)
    program_data = os.environ.get('ProgramData', 'C:\\ProgramData')
    jai_data_dir = os.path.join(program_data, 'jai agency')
    
    # Ensure the folder exists
    try:
        if not os.path.exists(jai_data_dir):
            os.makedirs(jai_data_dir, exist_ok=True)
        
        target_db = os.path.join(jai_data_dir, 'JAI_AGENCY.db')
        return target_db
    except Exception as e:
        # Fallback to local path if ProgramData is not accessible (e.g. dev or limited permissions)
        if getattr(sys, 'frozen', False):
            base_dir = os.path.dirname(sys.executable)
        else:
            base_dir = os.path.dirname(os.path.abspath(__file__))
        
        fallback_db = os.path.join(base_dir, 'JAI_AGENCY.db')
        print(f"Warning: Could not use ProgramData. Falling back to: {fallback_db}. Error: {e}")
        return fallback_db

DB_FILE = get_db_path()

def init_db_if_missing():
    """Ensure all required tables exist in the database."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # Products Table
    c.execute('''CREATE TABLE IF NOT EXISTS products (
        code TEXT PRIMARY KEY,
        name TEXT,
        name_ta TEXT,
        category TEXT,
        price REAL,
        unit TEXT DEFAULT 'PCS',
        bizz REAL DEFAULT 0,
        gst_percent REAL DEFAULT 0,
        reorder_level INTEGER DEFAULT 10,
        last_cost REAL DEFAULT 0,
        wholesale_price REAL DEFAULT 0
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
        supplier_id INTEGER,
        remarks TEXT,
        grade TEXT,
        product_name TEXT,
        unit TEXT,
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
        prev_total REAL DEFAULT 0,
        customer_name TEXT DEFAULT 'Walk-in',
        customer_mobile TEXT DEFAULT '',
        customer_id TEXT DEFAULT '',
        amount_paid REAL DEFAULT 0,
        balance REAL DEFAULT 0,
        source_bill_id INTEGER
    )''')

    # Sale Items Table
    c.execute('''CREATE TABLE IF NOT EXISTS sale_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        bill_id INTEGER,
        product_code TEXT,
        product_name TEXT,
        product_name_ta TEXT,
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

    # Expenses Table
    c.execute('''CREATE TABLE IF NOT EXISTS expenses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT,
        description TEXT,
        category TEXT,
        amount REAL,
        payment_method TEXT
    )''')

    # Credit Payments Table
    c.execute('''CREATE TABLE IF NOT EXISTS credit_payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        bill_id INTEGER,
        amount REAL,
        payment_method TEXT,
        date TEXT,
        FOREIGN KEY(bill_id) REFERENCES sales_log(id)
    )''')

    # Users Table
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT,
        role TEXT,
        full_name TEXT
    )''')

    # Insert Default Users if not exists
    c.execute('SELECT COUNT(*) FROM users')
    if c.fetchone()[0] == 0:
        default_users = [
            ('admin', 'admin123', 'admin', 'System Administrator'),
            ('sales', 'sales123', 'sales', 'Sales Executive'),
            ('inventory', 'inv123', 'inventory', 'Inventory Manager')
        ]
        c.executemany('INSERT INTO users (username, password, role, full_name) VALUES (?, ?, ?, ?)', default_users)

    conn.commit()
    conn.close()
    print("Database check/initialization complete.")

# Database initialization happens on import
init_db_if_missing()

# Data Containers (In-Memory Cache)
PRODUCTS = []
STORAGE = []
SALES_LOG = []
SUPPLIERS = []
RETURNS_LOG = []
EXPENSES = []

def get_db_connection():
    conn = sqlite3.connect(DB_FILE, timeout=30)
    conn.execute('PRAGMA journal_mode=WAL')
    conn.row_factory = sqlite3.Row
    return conn

def load_data():
    global PRODUCTS, STORAGE, SALES_LOG, SUPPLIERS, RETURNS_LOG
    
    conn = None
    try:
        conn = get_db_connection()
        
        # Load Products
        PRODUCTS = [dict(row) for row in conn.execute('SELECT * FROM products').fetchall()]
        
        # Load Storage
        raw_storage = [dict(row) for row in conn.execute('SELECT * FROM storage').fetchall()]
        STORAGE = []
        for s in raw_storage:
            # Map 'product_code' back to 'code' for app logic compatibility
            s['code'] = s['product_code']
            # Ensure name and unit are present (even if None in DB)
            if not s.get('product_name') or not s.get('unit'):
                # Fallback to products table for legacy data
                p = next((prod for prod in PRODUCTS if prod['code'] == s['code']), None)
                if not s.get('product_name'):
                    s['product_name'] = p['name'] if p else "Unknown"
                if not s.get('unit'):
                    s['unit'] = p['unit'] if p else "Nos"
            STORAGE.append(s)
        
        # Load Sales and Details
        sales_rows = conn.execute('SELECT * FROM sales_log').fetchall()
        SALES_LOG = []
        for row in sales_rows:
            sale = dict(row)
            # Fetch details
            details = [dict(item) for item in conn.execute('SELECT * FROM sale_items WHERE bill_id = ?', (sale['id'],)).fetchall()]
            formatted_details = []
            for d in details:
                # The app expects 'id' to contain the product code for bill details
                d['id'] = d['product_code'] 
                # Map product_name to name for report/preview consistency
                d['name'] = d.get('product_name', 'Unknown')
                d['name_ta'] = d.get('product_name_ta', '')
                formatted_details.append(d)
            
            sale['details'] = formatted_details
            SALES_LOG.append(sale)
            
        # Load Suppliers
        SUPPLIERS = [dict(row) for row in conn.execute('SELECT * FROM suppliers').fetchall()]
        
        # Load Returns
        raw_returns = [dict(row) for row in conn.execute('SELECT * FROM returns_log').fetchall()]
        RETURNS_LOG = []
        for r in raw_returns:
            RETURNS_LOG.append(r)
    
        # Load Expenses
        global EXPENSES
        EXPENSES = [dict(row) for row in conn.execute('SELECT * FROM expenses').fetchall()]
    finally:
        if conn: conn.close()

def run_migrations():
    """Ensure all required columns exist in the database."""
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # sales_log migrations
        columns = [info[1] for info in cur.execute("PRAGMA table_info(sales_log)").fetchall()]
        if 'prev_total' not in columns:
            cur.execute('ALTER TABLE sales_log ADD COLUMN prev_total REAL DEFAULT 0')
        if 'status' not in columns:
            cur.execute('ALTER TABLE sales_log ADD COLUMN status TEXT DEFAULT "ACTIVE"')
        if 'customer_name' not in columns:
            cur.execute('ALTER TABLE sales_log ADD COLUMN customer_name TEXT')
        if 'customer_mobile' not in columns:
            cur.execute('ALTER TABLE sales_log ADD COLUMN customer_mobile TEXT')
        if 'customer_id' not in columns:
            cur.execute('ALTER TABLE sales_log ADD COLUMN customer_id TEXT')
        if 'amount_paid' not in columns:
            cur.execute('ALTER TABLE sales_log ADD COLUMN amount_paid REAL DEFAULT 0')
        if 'balance' not in columns:
            cur.execute('ALTER TABLE sales_log ADD COLUMN balance REAL DEFAULT 0')
        if 'discount' not in columns:
            cur.execute('ALTER TABLE sales_log ADD COLUMN discount REAL DEFAULT 0')
        if 'gross_total' not in columns:
            cur.execute('ALTER TABLE sales_log ADD COLUMN gross_total REAL DEFAULT 0')
        if 'source_bill_id' not in columns:
            cur.execute('ALTER TABLE sales_log ADD COLUMN source_bill_id INTEGER')
            
        # sale_items migrations
        columns = [info[1] for info in cur.execute("PRAGMA table_info(sale_items)").fetchall()]
        if 'product_name_ta' not in columns:
            cur.execute('ALTER TABLE sale_items ADD COLUMN product_name_ta TEXT')
        if 'gst_percent' not in columns:
            cur.execute('ALTER TABLE sale_items ADD COLUMN gst_percent REAL DEFAULT 0')
        if 'igst_percent' not in columns:
            cur.execute('ALTER TABLE sale_items ADD COLUMN igst_percent REAL DEFAULT 0')
        if 'bizz' not in columns:
            cur.execute('ALTER TABLE sale_items ADD COLUMN bizz REAL DEFAULT 0')

        # products migrations
        columns = [info[1] for info in cur.execute("PRAGMA table_info(products)").fetchall()]
        if 'is_loose' not in columns:
            cur.execute('ALTER TABLE products ADD COLUMN is_loose INTEGER DEFAULT 0')
        if 'reorder_level' not in columns:
            cur.execute('ALTER TABLE products ADD COLUMN reorder_level INTEGER DEFAULT 10')
        if 'last_cost' not in columns:
            cur.execute('ALTER TABLE products ADD COLUMN last_cost REAL DEFAULT 0')
        if 'name_ta' not in columns:
            cur.execute('ALTER TABLE products ADD COLUMN name_ta TEXT')
        if 'price_per_gram' not in columns:
            cur.execute('ALTER TABLE products ADD COLUMN price_per_gram REAL DEFAULT 0')
        if 'unit' not in columns:
            cur.execute('ALTER TABLE products ADD COLUMN unit TEXT DEFAULT "PCS"')
        if 'wholesale_price' not in columns:
            cur.execute('ALTER TABLE products ADD COLUMN wholesale_price REAL DEFAULT 0')
        if 'gst_percent' not in columns:
            cur.execute('ALTER TABLE products ADD COLUMN gst_percent REAL DEFAULT 5')
        if 'igst_percent' not in columns:
            cur.execute('ALTER TABLE products ADD COLUMN igst_percent REAL DEFAULT 0')
        # Force existing 0s to 5 if the user just confirmed 5%
        cur.execute('UPDATE products SET gst_percent = 5 WHERE gst_percent == 0 OR gst_percent IS NULL')

        # storage migrations
        storage_columns = [info[1] for info in cur.execute("PRAGMA table_info(storage)").fetchall()]
        if 'remarks' not in storage_columns:
            cur.execute('ALTER TABLE storage ADD COLUMN remarks TEXT')
        if 'grade' not in storage_columns:
            cur.execute('ALTER TABLE storage ADD COLUMN grade TEXT')
        if 'product_name' not in storage_columns:
            cur.execute('ALTER TABLE storage ADD COLUMN product_name TEXT')
        if 'unit' not in storage_columns:
            cur.execute('ALTER TABLE storage ADD COLUMN unit TEXT')
        if 'supplier_id' not in storage_columns:
            cur.execute('ALTER TABLE storage ADD COLUMN supplier_id INTEGER')
        
        # credit_payments table migration
        cur.execute('''CREATE TABLE IF NOT EXISTS credit_payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bill_id INTEGER,
            amount REAL,
            payment_method TEXT,
            date TEXT,
            FOREIGN KEY(bill_id) REFERENCES sales_log(id)
        )''')
        
        conn.commit()
    except Exception as e:
        print(f"Migration Error: {e}")
    finally:
        conn.close()

# Run migrations and initial load
run_migrations()
load_data()

def get_aggregated_inventory():
    global PRODUCTS, STORAGE
    # Build a quick map of stock per product code
    stock_map = {}
    for b in STORAGE:
        code = str(b.get('code'))
        qty = float(b.get('qty', 0))
        stock_map[code] = stock_map.get(code, 0) + qty
        
    agg = []
    for p in PRODUCTS:
        code = str(p['code'])
        stock = stock_map.get(code, 0)
        
        # Latest cost and grade if available
        batches = [b for b in STORAGE if str(b.get('code')) == code]
        last_cost = p.get('last_cost', 0)
        grade = batches[-1].get('grade', 'N/A') if batches else 'N/A'
        
        # Attach batches with stock > 0 for the expanded view in Product Master
        item_batches = []
        for b in batches:
            if float(b.get('qty', 0)) > 0:
                b_fmt = b.copy()
                try:
                    e_obj = datetime.datetime.strptime(b['entry_time'], "%Y-%m-%d %H:%M:%S")
                    b_fmt['entry_time'] = e_obj.strftime("%d/%m/%Y %I:%M %p")
                except: pass
                
                if b.get('expiry') and b['expiry'] != '-':
                    try:
                        ex_obj = datetime.datetime.strptime(b['expiry'], "%Y-%m-%d")
                        b_fmt['expiry'] = ex_obj.strftime("%d/%m/%Y")
                    except: pass
                
                # Extract clean Batch No for display (Day of Year format: DDD)
                if '-' in b['batch_id']:
                    # Extract the first part which we will now set as %j
                    b_fmt['batch_no'] = b['batch_id'].split('-')[0]
                else:
                    b_fmt['batch_no'] = b['batch_id']
                item_batches.append(b_fmt)
        
        agg.append({
            'code': code,
            'name': p['name'],
            'grade': grade,
            'name_ta': p.get('name_ta', ''),
            'category': p.get('category', 'General'),
            'unit': p.get('unit', 'Nos'),
            'stock': stock,
            'price': p['price'],
            'price_per_gram': p.get('price_per_gram', 0),
            'last_cost': last_cost,
            'wholesale_price': p.get('wholesale_price', 0),
            'is_loose': p.get('is_loose', 0),
            'reorder_level': p.get('reorder_level', 10),
            'gst_percent': p.get('gst_percent', 0),
            'igst_percent': p.get('igst_percent', 0),
            'batches': item_batches
        })
    return agg


def save_data():
    load_data()

@app.route('/')
def login():
    # Provide simple anonymized stats for the login screen analytics
    today_str = datetime.datetime.now().strftime("%Y-%m-%d")
    yesterday_str = (datetime.datetime.now() - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    
    today_count = len([s for s in SALES_LOG if s['date'].startswith(today_str)])
    yesterday_count = len([s for s in SALES_LOG if s['date'].startswith(yesterday_str)])
    
    error = request.args.get('error')
    return render_template('login.html', 
                         login_stats={'today': today_count, 'yesterday': yesterday_count},
                         error=error)

@app.route('/auth', methods=['POST'])
def auth():
    username = request.form.get('username')
    password = request.form.get('password')
    
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE username = ? AND password = ?', (username, password)).fetchone()
    conn.close()
    
    if user:
        session['username'] = user['username']
        session['role'] = user['role']
        session['full_name'] = user['full_name']
        
        if user['role'] == 'admin':
            return redirect(url_for('admin_dashboard'))
        elif user['role'] == 'inventory':
            return redirect(url_for('inventory_dashboard'))
        elif user['role'] == 'sales':
            return redirect(url_for('billing_navigation'))
            
    return redirect(url_for('login', error='1'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/api/auth/update', methods=['POST'])
def update_auth():
    data = request.json
    role = data.get('role')
    old_user = data.get('old_username')
    old_pass = data.get('old_password')
    new_user = data.get('new_username')
    new_pass = data.get('new_password')
    
    if role not in ['inventory', 'sales']:
        return jsonify({'success': False, 'message': 'Unauthorized role update'})
        
    if not all([old_user, old_pass, new_user, new_pass]):
        return jsonify({'success': False, 'message': 'All fields are required'})
        
    conn = get_db_connection()
    # Verify current credentials
    user = conn.execute('SELECT * FROM users WHERE role = ? AND username = ? AND password = ?', 
                      (role, old_user, old_pass)).fetchone()
    
    if not user:
        conn.close()
        return jsonify({'success': False, 'message': 'Current credentials do not match'})
        
    try:
        conn.execute('UPDATE users SET username = ?, password = ? WHERE role = ?', (new_user, new_pass, role))
        conn.commit()
        return jsonify({'success': True, 'message': 'Authentication updated successfully'})
    except sqlite3.IntegrityError:
        return jsonify({'success': False, 'message': 'Username already taken'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})
    finally:
        conn.close()

@app.route('/admin')
def admin_dashboard():
    if session.get('role') != 'admin':
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    sales_rows = conn.execute('SELECT * FROM sales_log').fetchall()
    total_sales = sum(row['total'] for row in sales_rows)
    transactions = len(sales_rows)
    
    # Recent sales formatted for the template
    recent_sales = []
    for row in reversed(sales_rows[-10:]):
        try:
            d_obj = datetime.datetime.strptime(row['date'], "%Y-%m-%d %H:%M:%S")
            date_display = d_obj.strftime("%d/%m/%Y %I:%M %p")
        except:
            date_display = row['date']
            
        recent_sales.append({
            'id': row['id'],
            'date': date_display,
            'items': row['items_count'],
            'total': row['total']
        })
    conn.close()
    
    return render_template('admin.html', 
                         total_sales=total_sales, 
                         transactions=transactions, 
                         sales=recent_sales,
                         current_time=datetime.datetime.now().strftime("%d/%m/%Y, %I:%M %p"),
                         page='admin')

@app.route('/inventory')
def inventory_dashboard():
    if session.get('role') not in ['inventory', 'admin']:
        return redirect(url_for('login'))
    
    now = datetime.datetime.now()
    
    # 1. Low Stock Alerts (Threshold < 10)
    inventory = get_aggregated_inventory()
    low_stock_items = [item for item in inventory if item['stock'] < 10]
    
    # 2. Expiry Date Monitoring (Within 30 days)
    expiring_batches = []
    for batch in STORAGE:
        expiry_date_str = batch.get('expiry')
        if expiry_date_str and expiry_date_str != '-':
            try:
                expiry_dt = datetime.datetime.strptime(expiry_date_str, "%Y-%m-%d")
                days_to_expiry = (expiry_dt - now).days
                if days_to_expiry <= 30:
                    product = next((p for p in PRODUCTS if p['code'] == batch['code']), None)
                    expiring_batches.append({
                        'batch_id': batch['batch_id'].split('-')[0] if '-' in batch['batch_id'] else batch['batch_id'],
                        'name': product['name'] if product else "Unknown",
                        'date': expiry_dt.strftime("%d/%m/%Y"),
                        'days_remaining': days_to_expiry,
                        'status': "Expired" if days_to_expiry < 0 else "Expiring Soon"
                    })
            except Exception as e:
                print(f"Error parsing expiry date {expiry_date_str}: {e}")

    # Summary Stats
    stats = {
        'total_skus': len(PRODUCTS),
        'low_stock_count': len(low_stock_items),
        'expiring_count': len(expiring_batches),
        'total_stock_value': sum(item['stock'] * item['price'] for item in inventory)
    }

    # 3. Category Distribution Data
    category_map = {}
    for item in inventory:
        cat = item.get('category', 'Uncategorized')
        val = item['stock'] * item['price']
        category_map[cat] = category_map.get(cat, 0) + val
    
    cat_labels = list(category_map.keys())
    cat_values = list(category_map.values())

    # 4. Recent Stock Entry Trends (Last 7 Days)
    entry_trends = []
    trend_labels = []
    for i in range(6, -1, -1):
        day = (now - datetime.timedelta(days=i)).strftime("%Y-%m-%d")
        day_label = (now - datetime.timedelta(days=i)).strftime("%d %b")
        qty_added = sum(b['qty'] for b in STORAGE if b['entry_time'].startswith(day))
        trend_labels.append(day_label)
        entry_trends.append(qty_added)

    return render_template('inventory/dashboard.html', 
                           stats=stats, 
                           low_stock=low_stock_items[:5], # Show top 5
                           expiring=expiring_batches[:5], # Show top 5
                           cat_labels=cat_labels,
                           cat_values=cat_values,
                           entry_trends=entry_trends,
                           trend_labels=trend_labels,
                           page='dashboard')

@app.route('/inventory/invoices')
def inventory_invoices():
    if session.get('role') not in ['inventory', 'admin']:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    query = '''
        SELECT 
            s.invoice_no, 
            s.arrival_date,
            GROUP_CONCAT(s.product_name, ", ") as item_summary,
            SUM(s.qty) as total_qty,
            SUM(s.qty * s.cost) as total_cost,
            MAX(s.entry_time) as entry_time,
            MAX(sup.name) as supplier_name
        FROM storage s
        LEFT JOIN suppliers sup ON s.supplier_id = sup.id
        WHERE s.invoice_no != 'MANUAL-STORAGE' AND s.invoice_no NOT LIKE 'RET-%' AND s.invoice_no NOT LIKE 'CANCEL-%'
        GROUP BY s.invoice_no, s.arrival_date
        ORDER BY s.arrival_date DESC, s.entry_time DESC
    '''
    rows = conn.execute(query).fetchall()
    invoices = [dict(row) for row in rows]
    for inv in invoices:
        try:
            dt = datetime.datetime.strptime(inv['arrival_date'], "%Y-%m-%d")
            inv['date'] = dt.strftime("%d/%m/%Y")
        except:
            inv['date'] = inv['arrival_date']
        
        try:
            tm = datetime.datetime.strptime(inv['entry_time'], "%Y-%m-%d %H:%M:%S")
            inv['time'] = tm.strftime("%I:%M %p")
        except:
            inv['time'] = ""
            
    conn.close()
    return render_template('inventory/invoices.html', invoices=invoices, page='invoices')

@app.route('/inventory/invoice/add')
def inventory_invoice_add():
    if session.get('role') not in ['inventory', 'admin']:
        return redirect(url_for('login'))
    
    inventory = get_aggregated_inventory()
    # Simple list of suppliers
    conn = get_db_connection()
    suppliers = [dict(row) for row in conn.execute('SELECT * FROM suppliers').fetchall()]
    conn.close()
    
    return render_template('inventory/invoice_add.html', 
                          inventory=inventory, 
                          suppliers=suppliers,
                          today=datetime.datetime.now().strftime("%Y-%m-%d"),
                          page='invoices')

@app.route('/api/inventory/invoice/delete/<string:invoice_no>', methods=['POST'])
def api_delete_invoice(invoice_no):
    if session.get('role') not in ['inventory', 'admin']:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    conn = None
    try:
        conn = get_db_connection()
        conn.execute('DELETE FROM storage WHERE invoice_no = ?', (invoice_no,))
        conn.commit()
        load_data()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})
    finally:
        if conn: conn.close()

@app.route('/api/inventory/stock-entry', methods=['POST'])
def api_stock_entry():
    if session.get('role') not in ['inventory', 'admin']:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    data = request.json
    invoice_no = data.get('invoice_no')
    supplier_id = data.get('supplier_id')
    arrival_date = data.get('arrival_date', datetime.datetime.now().strftime("%Y-%m-%d"))
    items = data.get('items', [])
    
    if not invoice_no or not items:
        return jsonify({'success': False, 'message': 'Missing invoice number or items'})
        
    conn = None
    try:
        conn = get_db_connection()
        now = datetime.datetime.now()
        
        for item in items:
            code = item.get('code')
            name = item.get('name')
            qty = float(item.get('qty', 0))
            unit = item.get('unit', 'Nos')
            
            # 1. Fetch Master Data for this product
            master = conn.execute('SELECT last_cost, gst_percent FROM products WHERE code = ?', (code,)).fetchone()
            
            if master:
                cost = master['last_cost']
                gst_percent = master['gst_percent']
            else:
                # Completely New Product - Insert with placeholders
                cost = 0
                gst_percent = 0
                conn.execute('''INSERT INTO products (code, name, unit, price, last_cost, is_loose, gst_percent) 
                                VALUES (?, ?, ?, ?, ?, ?, ?)''',
                            (code, name, unit, 0, 0, 1 if unit.lower() in ['kg', 'ltr', 'gm', 'ml'] else 0, 0))
            
            # 2. Batch ID
            entry_time = now.strftime("%Y-%m-%d %H:%M:%S")
            batch_id = f"INV-{invoice_no}-{code}-{now.strftime('%H%M%S')}"
            
            # 3. Insert into storage
            conn.execute('''INSERT INTO storage (batch_id, product_code, qty, entry_time, arrival_date, expiry, cost, invoice_no, supplier_id, product_name, unit) 
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                        (batch_id, code, qty, entry_time, arrival_date, None, cost, invoice_no, supplier_id, name, unit))
            
        conn.commit()
        load_data()
        return jsonify({'success': True})
    except Exception as e:
        if conn: conn.rollback()
        return jsonify({'success': False, 'message': str(e)})
    finally:
        if conn: conn.close()


@app.route('/inventory/storage')
def inventory_storage_page():
    if session.get('role') not in ['inventory', 'admin']:
        return redirect(url_for('login'))
    
    # Flatten view of storage for the dedicated storage page
    storage_view = []
    for b in STORAGE:
        # User requested: Invoice entries show only in Live, not in Storage page.
        # Direct entries (MANUAL-STORAGE) show in both.
        if b.get('invoice_no') != 'MANUAL-STORAGE':
            continue
            
        prod = next((p for p in PRODUCTS if p['code'] == b['code']), None)
        item = b.copy()
        item['product_name'] = b.get('product_name') or (prod['name'] if prod else "Unknown")
        # Extract Batch No (Day of Year format: DDD)
        if '-' in b['batch_id']:
            item['batch_no'] = b['batch_id'].split('-')[0]
        else:
            item['batch_no'] = b['batch_id']
        # Date & Time Formatting for Display
        try:
            dt_obj = datetime.datetime.strptime(b['arrival_date'], "%Y-%m-%d")
            item['arrival_date'] = dt_obj.strftime("%d/%m/%Y")
        except: pass
        
        try:
            ent_obj = datetime.datetime.strptime(b['entry_time'], "%Y-%m-%d %H:%M:%S")
            item['time_only'] = ent_obj.strftime("%I:%M %p")
        except:
            item['time_only'] = b['entry_time'].split(' ')[1] if ' ' in b['entry_time'] else ''
            
        storage_view.append(item)
    
    # Sort by entry_time for FIFO display
    storage_view.sort(key=lambda x: x['entry_time'])
    
    return render_template('inventory/storage.html', storage_view=storage_view, page='storage')

@app.route('/inventory/storage/add')
def inventory_storage_add():
    if session.get('role') not in ['inventory', 'admin']:
        return redirect(url_for('login'))
    
    now = datetime.datetime.now()
    # Batch code based on Day of Year (DDD)
    batch_no = now.strftime('%j')
    time_only = now.strftime("%I:%M %p")
    
    return render_template('inventory/storage_add.html', 
                         batch_no=batch_no, 
                         time_only=time_only, 
                         today=now.strftime("%d/%m/%Y"),
                         products=PRODUCTS,
                         page='storage')

@app.route('/api/inventory/storage/add', methods=['POST'])
def api_inventory_storage_add():
    if session.get('role') not in ['inventory', 'admin']:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    data = request.json
    code = data.get('code')
    name = data.get('name')
    qty = float(data.get('qty', 0))
    cost = float(data.get('cost', 0))
    unit = data.get('unit', 'Kg')
    grade = data.get('grade', '')
    remarks = data.get('remarks', '')
    custom_time = data.get('entry_time')# YYYY-MM-DD HH:MM:SS
    gst_percent = float(data.get('gst_percent', 0))
    expiry = data.get('expiry') or None

    if not code or qty <= 0:
        return jsonify({'success': False, 'message': 'Invalid code or quantity'})

    conn = None
    try:
        conn = get_db_connection()
        # Determine is_loose based on unit
        is_loose = 1 if unit.lower() in ['kg', 'ltr', 'gm', 'ml'] else 0
        # Use provided selling price or fallback to markup
        price = float(data.get('price', cost * 1.5))
        
        # 1. Update/Add to products table
        conn.execute('''INSERT OR REPLACE INTO products (code, name, unit, price, last_cost, is_loose, category, gst_percent) 
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                    (code, name, unit, price, cost, is_loose, 'General', gst_percent))
        
        now = datetime.datetime.now()
        entry_time = custom_time if custom_time else now.strftime("%Y-%m-%d %H:%M:%S")
        arrival_date = entry_time.split(' ')[0]
        
        # 2. Generate batch ID (DDD-HHMMSS)
        dt_obj = datetime.datetime.strptime(entry_time, "%Y-%m-%d %H:%M:%S")
        batch_id = f"{dt_obj.strftime('%j')}-{dt_obj.strftime('%H%M%S')}"

        # 3. Insert into storage table
        conn.execute('''INSERT INTO storage (batch_id, product_code, qty, entry_time, arrival_date, expiry, cost, invoice_no, remarks, grade, product_name, unit) 
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                    (batch_id, code, qty, entry_time, arrival_date, expiry, cost, 'MANUAL-STORAGE', remarks, grade, name, unit))
        
        conn.commit()
        # 4. Refresh Memory Cache
        load_data()
        return jsonify({'success': True})
    except Exception as e:
        if conn: conn.rollback()
        print(f"Error in storage add: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        if conn: conn.close()

@app.route('/api/inventory/storage/edit/<int:id>', methods=['POST'])
def api_edit_storage(id):
    if session.get('role') not in ['inventory', 'admin']:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    data = request.json
    qty = float(data.get('qty', 0))
    grade = data.get('grade', '')
    remarks = data.get('remarks', '')
    code = data.get('code', '')
    unit = data.get('unit', '')
    expiry = data.get('expiry') or None

    conn = None
    try:
        conn = get_db_connection()
        conn.execute('UPDATE storage SET qty = ?, grade = ?, remarks = ?, product_code = ?, unit = ?, expiry = ? WHERE id = ?', 
                    (qty, grade, remarks, code, unit, expiry, id))
        conn.commit()
        load_data()
        return jsonify({'success': True})
    except Exception as e:
        if conn: conn.rollback()
        return jsonify({'success': False, 'message': str(e)})
    finally:
        if conn: conn.close()

@app.route('/api/inventory/storage/delete/<int:id>', methods=['POST'])
def api_delete_storage(id):
    if session.get('role') not in ['inventory', 'admin']:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    conn = None
    try:
        conn = get_db_connection()
        conn.execute('DELETE FROM storage WHERE id = ?', (id,))
        conn.commit()
        load_data()
        return jsonify({'success': True})
    except Exception as e:
        if conn: conn.rollback()
        return jsonify({'success': False, 'message': str(e)})
    finally:
        if conn: conn.close()

@app.route('/inventory/products')
def inventory_products():
    if session.get('role') not in ['inventory', 'admin']:
        return redirect(url_for('login'))
    return render_template('inventory/products.html', 
                          inventory=get_aggregated_inventory(),
                          today=datetime.datetime.now().strftime("%Y-%m-%d"),
                          page='products')


@app.route('/inventory/live-stock')
def live_stock():
    if session.get('role') not in ['inventory', 'admin']:
        return redirect(url_for('login'))
    
    today_str = datetime.datetime.now().strftime("%Y-%m-%d")
    today_sales = [s for s in SALES_LOG if s['date'].startswith(today_str)]
    
    # Identify all codes to show
    all_codes = set(str(p['code']) for p in PRODUCTS if p.get('code'))
    all_codes.update(str(b['code']) for b in STORAGE if b.get('code'))
    for sale in today_sales:
        for item in sale['details']:
            p_code = item.get('product_code') or item.get('id')
            if p_code:
                all_codes.add(str(p_code))
    
    live_data = []
    for code in all_codes:
        if not code or code == 'None': continue
        
        # Find description/name
        b_entry = next((b for b in STORAGE if str(b['code']) == code), None)
        p_entry = next((p for p in PRODUCTS if str(p['code']) == code), None)
        
        name = "Unknown"
        if b_entry and b_entry.get('product_name'):
            name = b_entry['product_name']
        elif p_entry:
            name = p_entry['name']
            
        closing_stock = sum(b['qty'] for b in STORAGE if str(b['code']) == code)
        
        # Outward = Sales Today
        outward_today = 0
        for sale in today_sales:
            for item in sale['details']:
                item_code = str(item.get('product_code') or item.get('id'))
                if item_code == code:
                    outward_today += item['qty']
        
        # Inward = Storage Entries + Returns Today
        inward_today = sum(b['qty'] for b in STORAGE if str(b['code']) == code and (
            b.get('arrival_date', '') == today_str or 
            b.get('entry_time', '').startswith(today_str)
        ))
        
        opening_stock = closing_stock + outward_today - inward_today
        
        # Only show if there is activity today OR if there is current stock
        if closing_stock > 0 or inward_today > 0 or outward_today > 0:
            live_data.append({
                'code': code,
                'name': name,
                'opening': round(opening_stock, 2),
                'in': round(inward_today, 2),
                'out': round(outward_today, 2),
                'closing': round(closing_stock, 2)
            })
    

        
    return render_template('inventory/live_stock.html', 
                          live_data=live_data, 
                          today=datetime.datetime.now().strftime("%d/%m/%Y"), 
                          page='live_stock')

@app.route('/api/purchase/delete/<purchase_id>', methods=['POST'])
def delete_purchase(purchase_id):
    if session.get('role') not in ['inventory', 'admin']:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    global STORAGE
    # Delete all batches that belong to this purchase ID
    # A purchase ID is the prefix of batch_id (bid.startswith(purchase_id + "-") or bid == purchase_id)
    new_storage = []
    for b in STORAGE:
        # Exact match or prefix match
        bid = b['batch_id']
        parts = bid.split('-')
        group_id = "-".join(parts[:2]) if len(parts) >= 2 else bid
        if group_id != purchase_id:
            new_storage.append(b)
            
    STORAGE = new_storage
    save_data()
    return jsonify({'success': True})

@app.route('/api/batch/delete/<batch_id>', methods=['POST'])
def delete_batch(batch_id):
    if session.get('role') not in ['inventory', 'admin']:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    global STORAGE
    STORAGE = [b for b in STORAGE if b['batch_id'] != batch_id]
    save_data()
    return jsonify({'success': True})

@app.route('/billing/navigation')
def billing_navigation():
    if session.get('role') not in ['sales', 'admin']:
        return redirect(url_for('login'))
    return render_template('billing/navigation.html', page='navigation')

@app.route('/billing')
def billing_pos():
    if session.get('role') not in ['sales', 'admin']:
        return redirect(url_for('login'))
    
    # Only show products that have actual stock available
    available_inventory = [item for item in get_aggregated_inventory() if item['stock'] > 0]
    next_bill_id = len(SALES_LOG) + 1
    
    today = datetime.datetime.now().strftime("%d/%m/%Y")
    
    # Load any pre-loaded cart from session (for returns/reprocessing)
    reprocess_cart = session.pop('reprocess_cart', [])
    
    # Fetch customers for search in POS
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''SELECT DISTINCT customer_id, customer_name, customer_mobile 
                   FROM sales_log 
                   WHERE (customer_mobile != "" OR customer_id != "")
                   ORDER BY customer_name''')
    customers = [dict(row) for row in cur.fetchall()]
    conn.close()
    
    return render_template('billing/pos.html', 
                           inventory=available_inventory, 
                           master_products=PRODUCTS,
                           next_bill_id=next_bill_id, 
                           today=today,
                           initial_cart=reprocess_cart,
                           customers=customers,
                           page='pos')

@app.route('/api/send-report', methods=['POST'])
def send_report_api():
    if session.get('role') not in ['sales', 'admin']:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
        
    try:
        success, message = mailer.send_report_email()
        return jsonify({'success': success, 'message': message})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/billing/dashboard')
def billing_dashboard():
    if session.get('role') not in ['sales', 'admin']:
        return redirect(url_for('login'))
    
    now = datetime.datetime.now()
    today_str = now.strftime("%Y-%m-%d")
    
    today_sales = [s for s in SALES_LOG if s['date'].startswith(today_str)]
    
    # If today is empty, show the most recent day's data for demo/testing purposes
    if not today_sales and SALES_LOG:
        latest_date = SALES_LOG[-1]['date'].split(" ")[0]
        today_sales = [s for s in SALES_LOG if s['date'].startswith(latest_date)]
        display_date_label = datetime.datetime.strptime(latest_date, "%Y-%m-%d").strftime("%d/%m/%Y")
    else:
        display_date_label = now.strftime("%d/%m/%Y")

    total_today = sum(s['total'] for s in today_sales)
    count_today = len(today_sales)

    # 7-Day Sales Data for Graph
    labels = []
    values = []
    for i in range(6, -1, -1):
        day = (now - datetime.timedelta(days=i)).strftime("%Y-%m-%d")
        day_label = (now - datetime.timedelta(days=i)).strftime("%d %b")
        day_total = sum(s['total'] for s in SALES_LOG if s['date'].startswith(day))
        labels.append(day_label)
        values.append(day_total)

    # Get recent sales for the Live Feed (Last 15)
    recent_activity = []
    for s in reversed(SALES_LOG[-15:]):
        # Extract time from "YYYY-MM-DD HH:MM:SS"
        try:
            time_display = datetime.datetime.strptime(s['date'], "%Y-%m-%d %H:%M:%S").strftime("%I:%M %p")
        except:
            time_display = s['date'].split(" ")[1] if " " in s['date'] else s['date']
            
        recent_activity.append({
            'id': s['id'],
            'time': time_display,
            'total': s['total'],
            'items_count': sum(item['qty'] for item in s['details'])
        })

    # Calculate Top Moving Product Today
    product_counts = {}
    for sale in today_sales:
        for item in sale['details']:
            name = item.get('name', 'Unknown')
            product_counts[name] = product_counts.get(name, 0) + item['qty']
    
    top_moving = "---"
    if product_counts:
        top_moving = max(product_counts, key=product_counts.get)

    # Inventory Alerts for Sales Dashboard
    inventory = get_aggregated_inventory()
    low_stock_count = len([item for item in inventory if item['stock'] < 10])
    
    expiring_count = 0
    for batch in STORAGE:
        expiry_date_str = batch.get('expiry')
        if expiry_date_str and expiry_date_str != '-':
            try:
                expiry_dt = datetime.datetime.strptime(expiry_date_str, "%Y-%m-%d")
                if (expiry_dt - now).days <= 30:
                    expiring_count += 1
            except: pass

    # Payment Split
    payment_split = {'CASH': 0, 'UPI': 0, 'CARD': 0, 'CREDIT': 0}
    for s in today_sales:
        pm = s.get('payment_method', 'CASH').upper()
        if pm in payment_split:
            payment_split[pm] += s['total']
        else:
            # Check if it was saved as 'CREDIT' or similar
            if 'CREDIT' in pm:
                payment_split['CREDIT'] += s['total']
            else:
                payment_split['CARD'] += s['total']

    # Include credit payments in totals and split
    conn = get_db_connection()
    try:
        cp_today = conn.execute("SELECT * FROM credit_payments WHERE date LIKE ?", (today_str + '%',)).fetchall()
        for cp in cp_today:
            total_today += cp['amount']
            pm = cp['payment_method'].upper()
            if pm in payment_split:
                payment_split[pm] += cp['amount']
    finally:
        conn.close()

    # Calculate average sale (now including partials)
    average_sale = total_today / count_today if count_today > 0 else 0

    # Detailed Inventory Alerts
    inventory = get_aggregated_inventory()
    low_stock_items = [item for item in inventory if item['stock'] < item['reorder_level']]
    low_stock_items.sort(key=lambda x: x['stock'])

    return render_template('billing/dashboard.html', 
                           total_today=total_today, 
                           count_today=count_today,
                           average_sale=average_sale,
                           payment_split=payment_split,
                           top_moving=top_moving,
                           chart_labels=labels,
                           chart_values=values,
                           recent_activity=recent_activity,
                           display_date=display_date_label,
                           low_stock_alert=len(low_stock_items),
                           low_stock_items=low_stock_items[:5],
                           page='dashboard')

def enrich_sales_data(sales_list):
    enriched = []
    for sale in sales_list:
        s_display = sale.copy() 
        
        # Calculate derived metrics
        gross_total = 0.0
        tax_total = 0.0
        cgst_total = 0.0
        sgst_total = 0.0
        original_details = sale.get('details', [])
        
        details_with_cat = []
        for item in original_details:
            # Re-fetch product info if needed or rely on stored data
            p_code = item.get('product_code') or item.get('id')
            prod = next((p for p in PRODUCTS if p['code'] == str(p_code)), None)
            cat = prod['category'] if prod else 'Unknown'
            
            # Use stored GST percent or get it from product if missing
            gst_p = float(item.get('gst_percent', 0))
            if gst_p == 0 and prod:
                gst_p = float(prod.get('gst_percent', 0))
                
            # Item calculation (INCLUSIVE FIX)
            qty = float(item.get('qty', 0))
            selling_price = float(item.get('price', 0)) # This is the Inclusive Price
            
            # Reverse calculate base price and tax
            base_price = selling_price / (1 + (gst_p / 100))
            item_total_base = qty * base_price
            item_total_inclusive = qty * selling_price
            item_tax = item_total_inclusive - item_total_base
            
            gross_total += item_total_base
            tax_total += item_tax
            cgst_total += item_tax / 2
            sgst_total += item_tax / 2
            
            i_copy = item.copy()
            i_copy['category'] = cat
            i_copy['price'] = base_price  # Show base price as "Rate"
            i_copy['gross_amount'] = item_total_base # Show base total as "Amount"
            i_copy['tax_amount'] = item_tax
            details_with_cat.append(i_copy)
            
        s_display['details'] = details_with_cat
        
        # Financials - ENSURE CANCELLED/RETURNED with 0 total are excluded from reports
        status = sale.get('status', 'ACTIVE')
        actual_total_db = float(sale.get('total', 0))
        
        # Determine if this row should be dimmed in UI
        s_display['is_voided'] = (status == 'CANCELLED' or (status == 'RETURNED' and actual_total_db <= 0.01))
        
        # The total reported is what's currently in the DB row
        report_total = actual_total_db
        
        # Use the actual discount stored in DB, do not re-calculate nonsensically
        s_display['discount'] = float(sale.get('discount', 0))
        
        # If it's voided, all contributing values should effectively be 0 for the report summation
        if s_display['is_voided']:
            s_display['gross_amount'] = 0
            s_display['tax_amount'] = 0
            s_display['total'] = 0
            s_display['net_amount'] = 0
        else:
            s_display['gross_amount'] = gross_total
            s_display['tax_amount'] = tax_total
            s_display['total'] = report_total
            s_display['net_amount'] = report_total
        
        try:
            date_str = sale.get('date', '')
            if date_str:
                d_obj = datetime.datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
            else:
                d_obj = None
        except:
            d_obj = None
            
        # Define discount_total for the s_display dictionary below
        discount_total = float(sale.get('discount', 0))
        if s_display['is_voided']:
            discount_total = 0
            
        s_display = {
            'id': sale.get('id'),
            'date': sale.get('date'),
            'date_only': d_obj.strftime("%d/%m/%Y") if d_obj else "N/A",
            'time_only': d_obj.strftime("%I:%M %p") if d_obj else "N/A",
            'items_count': sale.get('items_count', 0),
            'total': actual_total_db,      
            'net_total': 0 if s_display['is_voided'] else report_total,    
            'net_amount': 0 if s_display['is_voided'] else report_total,    
            'subtotal': 0 if s_display['is_voided'] else gross_total,
            'gross_total': 0 if s_display['is_voided'] else gross_total,
            'gross_amount': 0 if s_display['is_voided'] else gross_total,
            'tax_total': 0 if s_display['is_voided'] else tax_total,
            'cgst_total': 0 if s_display['is_voided'] else cgst_total,
            'sgst_total': 0 if s_display['is_voided'] else sgst_total,
            'discount_total': discount_total,
            'discount': discount_total, # For templates that use 'discount'
            'is_voided': s_display['is_voided'],
            'payment_method': sale.get('payment_method', 'CASH'),
            'status': status,
            'customer_name': sale.get('customer_name', 'Walk-in'),
            'customer_mobile': sale.get('customer_mobile', ''),
            'customer_id': sale.get('customer_id', ''),
            'amount_paid': float(sale.get('amount_paid', 0)),
            'balance': float(sale.get('balance', 0)),
            'source_bill_id': sale.get('source_bill_id'),
            'details': details_with_cat
        }
        
        enriched.append(s_display)
    return enriched

def get_payment_report_data(payment_method):
    """Combines original bills and partial credit payments for a specific method."""
    # 1. Full bills where this is the primary method (but NOT credit)
    primary_sales = [s for s in SALES_LOG if s.get('payment_method') == payment_method and s.get('status') != 'CANCELLED']
    enriched = enrich_sales_data(primary_sales)
    
    # 2. Add partial payments from credit_payments table
    conn = get_db_connection()
    try:
        # We join with sales_log to get the customer name for the report
        query = '''
            SELECT cp.*, sl.customer_name 
            FROM credit_payments cp
            JOIN sales_log sl ON cp.bill_id = sl.id
            WHERE cp.payment_method = ?
        '''
        partials = conn.execute(query, (payment_method,)).fetchall()
        
        for p in partials:
            try:
                dt_obj = datetime.datetime.strptime(p['date'], "%Y-%m-%d %H:%M:%S")
                date_only = dt_obj.strftime("%d/%m/%Y")
                time_only = dt_obj.strftime("%I:%M %p")
            except:
                date_only = p['date'].split(' ')[0]
                time_only = p['date'].split(' ')[1] if ' ' in p['date'] else ''

            enriched.append({
                'id': f"{p['bill_id']} (Part)",
                'date_only': date_only,
                'time_only': time_only,
                'net_total': p['amount'],
                'customer_name': p['customer_name'] or "Walk-in",
                'status': 'ACTIVE', # Treat as active for summation in templates
                'is_partial': True
            })
    finally:
        conn.close()
        
    # Sort by date/time if possible (optional, but good for reports)
    # Since enriched has mixed structures, we might just leave it appended or sort by date_only if needed.
    return enriched

@app.route('/billing/reports')
def billing_reports():
    if session.get('role') != 'sales': return redirect(url_for('login'))
    enriched = enrich_sales_data(SALES_LOG)
    return render_template('billing/reports.html', sales=enriched, page='reports')

# --- New Separate Report Pages ---

@app.route('/billing/reports/sales-bill')
def report_sales_bill():
    if session.get('role') != 'sales': return redirect(url_for('login'))
    # Billwise Sales Report: exclude Cancelled by default, support date range
    from_date = request.args.get('from', datetime.datetime.now().strftime('%Y-%m-%d'))
    to_date = request.args.get('to', datetime.datetime.now().strftime('%Y-%m-%d'))
    bill_id = request.args.get('bill_id', '').strip()
    
    filtered = []
    for s in SALES_LOG:
        if s.get('status') == 'CANCELLED': continue
        
        # Date Filter
        s_date_str = s.get('date', '').split(' ')[0]
        date_match = (from_date <= s_date_str <= to_date)
        
        # Bill ID Filter (if provided)
        bill_match = True
        if bill_id:
            bill_match = (str(s.get('id')) == bill_id.replace('#', ''))
            
        if date_match and bill_match:
            filtered.append(s)
            
    enriched = enrich_sales_data(filtered)
    return render_template('billing/sales_bill_report.html', 
                          title='Billwise Sales Report', 
                          data=enriched,
                          from_date_raw=from_date,
                          to_date_raw=to_date,
                          bill_id=bill_id,
                          date_from=datetime.datetime.strptime(from_date, '%Y-%m-%d').strftime('%d/%m/%Y'),
                          date_to=datetime.datetime.strptime(to_date, '%Y-%m-%d').strftime('%d/%m/%Y'))

@app.route('/billing/reports/detail-bill')
def report_detail_bill():
    if session.get('role') != 'sales': return redirect(url_for('login'))
    # Sales Report: Show all including cancelled for audit? Or just all? Let's show All.
    enriched = enrich_sales_data(SALES_LOG)
    return render_template('billing/detail_bill_report.html', title='Sales Report', data=enriched)

@app.route('/billing/reports/cancelled')
def report_cancelled():
    if session.get('role') != 'sales': return redirect(url_for('login'))
    filtered = [s for s in SALES_LOG if s.get('status') == 'CANCELLED']
    enriched = enrich_sales_data(filtered)
    return render_template('billing/cancelled_bill_report.html', title='Cancelled Bills', data=enriched)

@app.route('/billing/reports/returns')
def report_returns_log():
    # Note: differs from /billing/returns which is the ACTION page. This is the LOG page.
    if session.get('role') != 'sales': return redirect(url_for('login'))
    return render_template('billing/return_bills_report.html', title='Return Bill Report', data=RETURNS_LOG, now=datetime.datetime.now())

@app.route('/billing/reports/return-bills')
def report_return_bills():
    if session.get('role') != 'sales': return redirect(url_for('login'))
    # Using a dedicated template for consistency with other report pages
    return render_template('billing/return_bills_report.html', title='Return Bills', data=RETURNS_LOG, now=datetime.datetime.now())

@app.route('/billing/reports/profit')
def report_profit():
    if session.get('role') != 'sales': return redirect(url_for('login'))
    
    from_date = request.args.get('from', datetime.datetime.now().strftime('%Y-%m-%d'))
    to_date = request.args.get('to', datetime.datetime.now().strftime('%Y-%m-%d'))
    
    # Pre-map products for fast lookup (ensure string keys)
    product_map = {str(p['code']): p for p in PRODUCTS}
    
    profit_data = []
    item_log = []
    product_summary = {}
    
    total_sales_val = 0
    total_cost_val = 0
    total_profit_val = 0
    
    for s in SALES_LOG:
        if s.get('status') == 'CANCELLED': continue
        
        s_date_str = s.get('date', '').split(' ')[0]
        if from_date <= s_date_str <= to_date:
            sale_profit = 0
            sale_cost = 0
            
            # Enrich details with profit
            items = s.get('details', [])
            for item in items:
                p_code = item.get('id')
                if not p_code: p_code = item.get('product_code')
                
                master_p = product_map.get(str(p_code), {})
                purchase_price = master_p.get('last_cost', 0)
                selling_price = item.get('price', 0)
                qty = item.get('qty', 0)
                
                item_cost = purchase_price * qty
                item_sales = selling_price * qty
                item_profit = item_sales - item_cost
                
                sale_cost += item_cost
                sale_profit += item_profit
                
                p_name = item.get('name', 'Unknown')
                
                # Update product summary
                if p_code not in product_summary:
                    product_summary[p_code] = {
                        'name': p_name,
                        'qty': 0,
                        'revenue': 0,
                        'cost': 0,
                        'profit': 0
                    }
                product_summary[p_code]['qty'] += qty
                product_summary[p_code]['revenue'] += item_sales
                product_summary[p_code]['cost'] += item_cost
                product_summary[p_code]['profit'] += item_profit
                
                item_log.append({
                    'id': s['id'],
                    'date': s['date'],
                    'customer': s.get('customer_name', 'Walk-in'),
                    'product_name': p_name,
                    'qty': qty,
                    'revenue': item_sales,
                    'cost': item_cost,
                    'profit': item_profit
                })
            
            actual_revenue = s.get('total', 0)
            total_sales_val += actual_revenue
            total_cost_val += sale_cost
            total_profit_val += sale_profit
            
            profit_data.append({
                'id': s['id'],
                'date': s['date'],
                'customer': s.get('customer_name', 'Walk-in'),
                'revenue': actual_revenue,
                'cost': sale_cost,
                'profit': sale_profit
            })

    return render_template('billing/profit_report.html',  
                          title='Profit Analysis Report',
                          data=profit_data,
                          item_log=item_log,
                          summary=sorted(product_summary.values(), key=lambda x: x['profit'], reverse=True),
                          total_revenue=total_sales_val,
                          total_cost=total_cost_val,
                          total_profit=total_profit_val,
                          from_date_raw=from_date,
                          to_date_raw=to_date,
                          date_from=datetime.datetime.strptime(from_date, '%Y-%m-%d').strftime('%d/%m/%Y'),
                          date_to=datetime.datetime.strptime(to_date, '%Y-%m-%d').strftime('%d/%m/%Y'))

@app.route('/billing/reports/correction')
def report_correction():
    if session.get('role') != 'sales': return redirect(url_for('login'))
    filtered = [s for s in SALES_LOG if s.get('status') == 'CORRECTION']
    enriched = enrich_sales_data(filtered)
    return render_template('billing/correction_bill_report.html', title='Correction Bills', data=enriched)

@app.route('/billing/expenses')
def billing_expenses():
    if session.get('role') != 'sales': return redirect(url_for('login'))
    display_expenses = []
    for e in EXPENSES:
        ec = e.copy()
        try:
            dt = datetime.datetime.strptime(e.get('date', ''), "%Y-%m-%d")
            ec['date'] = dt.strftime("%d/%m/%Y")
        except: pass
        display_expenses.append(ec)
        
    return render_template('billing/expenses.html', expenses=display_expenses, title='Daily Expenses', page='expenses', now=datetime.datetime.now())

# Translation mapping for Bills
BILL_TRANSLATIONS = {
    'Bill': 'Bill',
    'Date': 'Date',
    'Time': 'Time',
    'Customer': 'Customer',
    'Item': 'Item',
    'Qty': 'Qty',
    'Total': 'Total',
    'Gross Total': 'Gross Total',
    'Discount': 'Discount',
    'Net Amount': 'Net Amount',
    'Payment': 'Payment',
    'Balance': 'Balance',
    'Thank You': 'Thank You, Visit Again!'
}

@app.route('/billing/print-receipt/<int:sale_id>')
def print_receipt(sale_id):
    if not session.get('role'): return redirect(url_for('login'))
    sale = next((s for s in SALES_LOG if s['id'] == sale_id), None)
    if not sale: return "Bill Not Found", 404
    enriched = enrich_sales_data([sale])[0]
    return render_template('billing/invoice_a5.html', sale=enriched, t=BILL_TRANSLATIONS)

@app.route('/api/expenses/add', methods=['POST'])
def add_expense():
    if session.get('role') != 'sales': return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    data = request.json
    date = data.get('date', datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    description = data.get('description')
    category = data.get('category', 'General')
    amount = float(data.get('amount', 0))
    payment_method = data.get('payment_method', 'CASH')
    
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('INSERT INTO expenses (date, description, category, amount, payment_method) VALUES (?, ?, ?, ?, ?)',
                    (date, description, category, amount, payment_method))
        conn.commit()
    except Exception as e:
        if conn: conn.rollback()
        return jsonify({'success': False, 'message': str(e)})
    finally:
        if conn: conn.close()
    
    load_data() # Refresh cache
    return jsonify({'success': True})

@app.route('/api/expenses/delete/<int:id>', methods=['POST'])
def delete_expense(id):
    if session.get('role') != 'sales': return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('DELETE FROM expenses WHERE id = ?', (id,))
        conn.commit()
    except Exception as e:
        if conn: conn.rollback()
        return jsonify({'success': False, 'message': str(e)})
    finally:
        if conn: conn.close()
    load_data()
    return jsonify({'success': True})

@app.route('/billing/reports/credit-bills')
def report_credit_bills():
    if session.get('role') not in ['admin', 'sales']: return redirect(url_for('login'))
    # Mapped to CARD payment
    data = get_payment_report_data('CARD')
    return render_template('billing/credit_bill_report.html', title='Card Sales', data=data)

@app.route('/billing/reports/cash-bills')
def report_cash_bills():
    if session.get('role') not in ['admin', 'sales']: return redirect(url_for('login'))
    data = get_payment_report_data('CASH')
    return render_template('billing/cash_bill_report.html', title='Cash Sales', data=data)

@app.route('/billing/reports/upi-bills')
def report_upi_bills():
    if session.get('role') not in ['admin', 'sales']: return redirect(url_for('login'))
    data = get_payment_report_data('UPI')
    return render_template('billing/upi_bill_report.html', title='UPI Sales Report', data=data)

@app.route('/billing/reports/compliments')
def report_compliments():
    if session.get('role') not in ['admin', 'sales']: return redirect(url_for('login'))
    data = get_payment_report_data('COMPLIMENT')
    return render_template('billing/compliment_report.html', title='Complimentary Gifts', data=data)

@app.route('/billing/reports/final')
def report_final():
    if session.get('role') not in ['sales', 'admin']:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    
    # 1. Determine Target Date
    target_date = request.args.get('date')
    if not target_date:
        target_date = datetime.datetime.now().strftime("%Y-%m-%d")
        # Fallback to last sale date if today is empty
        sales_check = conn.execute("SELECT COUNT(*) FROM sales_log WHERE date LIKE ?", (target_date + '%',)).fetchone()[0]
        if sales_check == 0:
            last_sale = conn.execute("SELECT date FROM sales_log ORDER BY date DESC LIMIT 1").fetchone()
            if last_sale:
                target_date = last_sale['date'].split(' ')[0]
    
    # 2. Sequential Database Lookups (Consolidated at the top)
    # Fetch direct sales
    sales_rows = [dict(r) for r in conn.execute("SELECT * FROM sales_log WHERE date LIKE ? AND status IN ('ACTIVE', 'RETURNED', 'PAID', 'CORRECTION')", (target_date + '%',)).fetchall()]
    
    # Fetch Expenses
    expenses_rows = [dict(r) for r in conn.execute("SELECT * FROM expenses WHERE date LIKE ?", (target_date + '%',)).fetchall()]
    
    # Fetch Credit Settlements
    settlements_rows = [dict(r) for r in conn.execute("SELECT * FROM credit_payments WHERE date LIKE ?", (target_date + '%',)).fetchall()]
    
    conn.close()

    # 3. Calculation Logic
    cash_collected = 0
    upi_collected = 0
    card_collected = 0
    credit_value_issued = 0
    compliment_count = 0
    
    # Process New Bills
    for s in sales_rows:
        pm = str(s.get('payment_method')).upper()
        amt_paid = float(s.get('amount_paid', 0))
        total_bill = float(s.get('total', 0))
        
        if pm == 'CASH': cash_collected += total_bill
        elif pm == 'UPI': upi_collected += total_bill
        elif pm == 'CARD': card_collected += total_bill
        elif pm == 'COMPLIMENT': compliment_count += 1
        elif pm == 'CREDIT':
            # For credit bills, we count the partial payment as cash/upi (default to cash in this summary)
            # and track the remaining balance separately.
            cash_collected += amt_paid 
            credit_value_issued += float(s.get('balance', 0))

    # Process Settlements (Payments for old credit bills)
    for cp in settlements_rows:
        pm = str(cp['payment_method']).upper()
        amt = float(cp.get('amount', 0))
        
        if pm == 'CASH': cash_collected += amt
        elif pm == 'UPI': upi_collected += amt
        elif pm == 'CARD': card_collected += amt

    # Process Expenses
    total_expenses = sum(e.get('amount', 0) for e in expenses_rows)

    # 4. Final Formatting & Return
    try:
        display_date = datetime.datetime.strptime(target_date, "%Y-%m-%d").strftime("%d/%m/%Y")
    except:
        display_date = target_date

    return render_template('billing/final_report.html', 
                           report_date=target_date,
                           report_date_display=display_date,
                           cash_sales=cash_collected,
                           upi_sales=upi_collected,
                           card_sales=card_collected,
                           credit_sales=credit_value_issued,
                           compliment_count=compliment_count,
                           expenses=expenses_rows,
                           total_expenses=total_expenses,
                           page='reports')


@app.route('/billing/reports/credit-sales')
def report_credit_sales():
    if session.get('role') != 'sales': return redirect(url_for('login'))
    # Filter for CREDIT sales that have a balance > 0 or are not marked as PAID
    filtered = [s for s in SALES_LOG if s.get('payment_method') == 'CREDIT' and s.get('status') != 'PAID']
    enriched = enrich_sales_data(filtered)
    
    # Fetch customers for the 'Add Legacy Credit' modal
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''SELECT DISTINCT customer_id, customer_name, customer_mobile 
                   FROM sales_log 
                   WHERE (customer_mobile != "" OR customer_id != "")
                   ORDER BY customer_name''')
    customers = [dict(row) for row in cur.fetchall()]
    conn.close()
    
    return render_template('billing/credit_sales_report.html', title='Credit Sales', data=enriched, customers=customers)

@app.route('/api/billing/pay-credit', methods=['POST'])
def pay_credit():
    if session.get('role') not in ['sales', 'admin']:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    data = request.json
    bill_id = data.get('bill_id')
    amount = float(data.get('amount', 0))
    pm = data.get('payment_method', 'CASH').upper()
    
    if amount <= 0:
        return jsonify({'success': False, 'message': 'Invalid amount'})
        
    sale = next((s for s in SALES_LOG if s['id'] == bill_id), None)
    if not sale:
        return jsonify({'success': False, 'message': 'Bill not found'})
        
    if amount > float(sale.get('balance', 0)):
        return jsonify({'success': False, 'message': 'Amount exceeds balance'})

    new_amount_paid = float(sale.get('amount_paid', 0)) + amount
    new_balance = float(sale.get('balance', 0)) - amount
    new_status = sale.get('status', 'PENDING')
    
    if new_balance <= 0:
        new_balance = 0
        new_status = 'PAID'

    now_ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # DB Persistence
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute('UPDATE sales_log SET amount_paid = ?, balance = ?, status = ? WHERE id = ?', 
                    (new_amount_paid, new_balance, new_status, bill_id))
        
        # Record the individual payment
        cur.execute('INSERT INTO credit_payments (bill_id, amount, payment_method, date) VALUES (?, ?, ?, ?)',
                    (bill_id, amount, pm, now_ts))
        
        conn.commit()
        
        # Update in-memory cache
        sale['amount_paid'] = new_amount_paid
        sale['balance'] = new_balance
        sale['status'] = new_status
        
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'message': str(e)})
    finally:
        conn.close()
        
    return jsonify({'success': True})

@app.route('/billing/reports/clients')
def report_clients():
    if session.get('role') != 'sales': return redirect(url_for('login'))
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''SELECT DISTINCT customer_id, customer_name, customer_mobile 
                   FROM sales_log 
                   WHERE (customer_mobile != "" OR customer_id != "")
                   ORDER BY customer_name''')
    customers = [dict(row) for row in cur.fetchall()]
    conn.close()
    return render_template('billing/clients_report.html', title='Client Directory', customers=customers)

@app.route('/api/billing/add-legacy-credit', methods=['POST'])
def api_add_legacy_credit():
    if session.get('role') not in ['sales', 'admin']:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
        
    data = request.json
    name = data.get('customer_name')
    mobile = data.get('customer_mobile', '')
    cust_id = data.get('customer_id', '')
    amount = float(data.get('amount', 0))
    date = data.get('date') # YYYY-MM-DD
    remarks = data.get('remarks', 'Opening Balance')
    
    if not name or amount <= 0:
        return jsonify({'success': False, 'message': 'Invalid data'})

    # Create a dummy bill record in sales_log
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''INSERT INTO sales_log 
                   (date, items_count, total, payment_method, status, customer_name, customer_mobile, customer_id, amount_paid, balance) 
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (f"{date} 00:00:00", 0, amount, 'CREDIT', 'PENDING', name, mobile, cust_id, 0, amount))
    conn.commit()
    conn.close()
    
    load_data()
    return jsonify({'success': True})

@app.route('/api/billing/finish-credit', methods=['POST'])
def finish_credit():
    if session.get('role') not in ['sales', 'admin']:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    data = request.json
    bill_id = data.get('bill_id')
    pm = data.get('payment_method', 'CASH').upper() # Default to cash if not provided
    
    sale = next((s for s in SALES_LOG if s['id'] == bill_id), None)
    if not sale:
        return jsonify({'success': False, 'message': 'Bill not found'})
        
    amount_to_pay = float(sale.get('balance', 0))
    new_amount_paid = float(sale.get('total', 0))
    new_balance = 0.0
    new_status = 'PAID'

    now_ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # DB Persistence
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute('UPDATE sales_log SET amount_paid = ?, balance = ?, status = ? WHERE id = ?', 
                    (new_amount_paid, new_balance, new_status, bill_id))
        
        # Record the individual payment
        if amount_to_pay > 0:
            cur.execute('INSERT INTO credit_payments (bill_id, amount, payment_method, date) VALUES (?, ?, ?, ?)',
                        (bill_id, amount_to_pay, pm, now_ts))
            
        conn.commit()
        
        # Update in-memory cache
        sale['amount_paid'] = new_amount_paid
        sale['balance'] = new_balance
        sale['status'] = new_status
        
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'message': str(e)})
    finally:
        conn.close()
        
    return jsonify({'success': True})

@app.route('/billing/returns')
def billing_returns():
    if session.get('role') not in ['sales', 'admin']:
        return redirect(url_for('login'))
    return render_template('billing/returns.html', sales=SALES_LOG, page='returns')

# Duplicate route removed
@app.route('/api/billing/bill/<int:bill_id>')
def get_bill_details(bill_id):
    sale = next((s for s in SALES_LOG if s['id'] == bill_id), None)
    if sale:
        return jsonify({'success': True, 'bill': sale})
    return jsonify({'success': False, 'message': 'Bill not found'})

@app.route('/api/billing/return-item', methods=['POST'])
def return_bill_item():
    if session.get('role') not in ['sales', 'admin']:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    data = request.json
    bill_id = data.get('bill_id')
    item_id = str(data.get('item_id'))
    qty_to_return = float(data.get('qty', 0))
    
    sale = next((s for s in SALES_LOG if s['id'] == bill_id), None)
    if not sale:
        return jsonify({'success': False, 'message': 'Bill not found'})
    
    if sale.get('status') == 'CANCELLED':
        return jsonify({'success': False, 'message': 'Cannot return items from a cancelled bill'})
    
    # 1. More robust item lookup using multiple possible keys (id, product_code, code)
    # 2. Fallback to index-based lookup if item_id is 'undefined' or a number that doesn't match a code
    item = None
    if item_id and item_id != 'undefined':
        item = next((i for i in sale['details'] if str(i.get('id') or i.get('product_code', '') or i.get('code', '')) == item_id), None)
    
    # Ultimate fallback: If the frontend sends an index or if the above failed
    if not item:
        try:
            # Try to see if item_id was acting as a numeric index from the frontend
            idx = int(item_id)
            if 0 <= idx < len(sale['details']):
                item = sale['details'][idx]
        except:
            pass

    if not item:
        return jsonify({'success': False, 'message': 'Item not found in bill. If the ID is missing, please contact administrator.'})
    
    if qty_to_return <= 0:
        return jsonify({'success': False, 'message': 'Invalid quantity'})

    if qty_to_return > item['qty']:
        return jsonify({'success': False, 'message': f"Return quantity ({qty_to_return}) exceeds purchased quantity ({item['qty']})"})
    
    # 1. Update In-Memory Stock (STORAGE)
    now = datetime.datetime.now()
    product = next((p for p in PRODUCTS if p['code'] == item_id), None)
    # Try to find the original cost or last cost for stock accuracy
    cost = 0.0
    if product:
        # Search consolidated inventory for last cost
        agg = get_aggregated_inventory()
        p_agg = next((x for x in agg if x['code'] == item_id), None)
        cost = p_agg['last_cost'] if p_agg else 0.0

    batch_id = f"RET-#{bill_id}-{now.strftime('%H%M%S')}"
    STORAGE.append({
        'batch_id': batch_id,
        'code': item_id,
        'qty': qty_to_return,
        'entry_time': now.strftime("%Y-%m-%d %H:%M:%S"),
        'arrival_date': now.strftime("%Y-%m-%d"),
        'expiry': None,
        'cost': cost, 
        'invoice_no': f"RET-#{bill_id}"
    })
    
    # 2. Update Financials
    item_price = float(item.get('price', 0))
    refund_amount = item_price * qty_to_return
    
    item['qty'] -= qty_to_return
    sale['total'] -= refund_amount
    
    # Update status to RETURNED or CANCELLED if all items returned
    if sale.get('status') != 'CANCELLED':
        if sale['total'] <= 0.01: # Check for floating point near zero
            sale['status'] = 'CANCELLED'
            sale['total'] = 0
            sale['balance'] = 0
        else:
            sale['status'] = 'RETURNED'
        
    # If credit sale, update balance too
    if sale.get('payment_method') == 'CREDIT':
        sale['balance'] = max(0.0, sale.get('balance', 0.0) - refund_amount)
    
    # 3. DB Persistence
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # Update sale items
        cur.execute('UPDATE sale_items SET qty = ? WHERE bill_id = ? AND product_code = ?', (item['qty'], bill_id, item_id))
        # Update sale log (including status)
        cur.execute('UPDATE sales_log SET total = ?, balance = ?, status = ? WHERE id = ?', (sale['total'], sale.get('balance', 0), sale['status'], bill_id))
        
        # Log the return
        return_date = now.strftime("%Y-%m-%d %H:%M:%S")
        cur.execute('INSERT INTO returns_log (date, product_code, product_name, qty, refund_amount, bill_id, type) VALUES (?, ?, ?, ?, ?, ?, ?)',
                    (return_date, item_id, item.get('name', 'Unknown'), qty_to_return, refund_amount, bill_id, 'PARTIAL_RETURN'))
        
        # Update storage (Rewrite table to keep synced with in-memory app logic)
        cur.execute('DELETE FROM storage')
        for b in STORAGE:
             cur.execute('INSERT INTO storage (batch_id, product_code, qty, entry_time, arrival_date, expiry, cost, invoice_no, remarks, grade, product_name, unit) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                      (b.get('batch_id'), b.get('code'), b.get('qty', 0), b.get('entry_time'), b.get('arrival_date'), b.get('expiry'), b.get('cost', 0), b.get('invoice_no'), b.get('remarks'), b.get('grade'), b.get('product_name'), b.get('unit')))
        
        conn.commit()
        
        # Update in-memory Returns Log
        RETURNS_LOG.append({
            'date': return_date,
            'type': 'PARTIAL_RETURN',
            'bill_id': bill_id,
            'product_code': item_id,
            'product_name': item.get('name', 'Unknown'),
            'qty': qty_to_return,
            'refund_amount': refund_amount
        })

        # Handle Reprocessing (Moving to Billing for new bill)
        if data.get('reprocess'):
            if 'reprocess_cart' not in session:
                session['reprocess_cart'] = []
            
            # Fetch rich product data for re-billing accuracy
            inv = get_aggregated_inventory()
            
            # Try to find product by code in inventory or in raw master PRODUCTS
            # Ensure we match as strings to avoid TypeErrors
            p_id_str = str(item_id)
            p_data = next((x for x in inv if str(x['code']) == p_id_str), None)
            if not p_data:
                p_data = next((p for p in PRODUCTS if str(p['code']) == p_id_str), None)
            
            # Determine the best available name and price
            # Priority for Name: Master Product Name -> Item Name -> Fallback
            r_name = p_data.get('name') if p_data else item.get('name', 'Unknown')
            if r_name in ['Stock Entry', 'Unknown', 'N/A', ''] and item.get('name'):
                r_name = item.get('name')
                
            # Priority for Price: Master Price -> Item recorded price
            # We prefer Master price to ensure re-billing uses current valid rates 
            # unless the bill item has a valid non-zero rate.
            r_price = float(p_data.get('price', 0)) if p_data else 0
            if r_price <= 0:
                r_price = float(item.get('price', 0))
            
            # Add to cart
            session['reprocess_cart'].append({
                'id': p_id_str,
                'code': p_id_str,
                'name': r_name,
                'price': r_price,
                'qty': qty_to_return,
                'unit': item.get('unit') or (p_data.get('unit') if p_data else 'PCS'),
                'stock': p_data.get('stock', 999) if p_data and 'stock' in p_data else 999,
                'grade': p_data.get('grade', 'N/A') if p_data and 'grade' in p_data else 'N/A',
                'gst_percent': p_data.get('gst_percent', 5) if p_data else 5
            })
            session.modified = True

    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'message': str(e)})
    finally:
        conn.close()

    return jsonify({'success': True, 'new_total': sale['total']})

@app.route('/api/billing/cancel-bill', methods=['POST'])
def cancel_bill():
    if session.get('role') not in ['sales', 'admin']:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    data = request.json
    bill_id = data.get('bill_id')
    
    sale = next((s for s in SALES_LOG if s['id'] == bill_id), None)
    if not sale:
        return jsonify({'success': False, 'message': 'Bill not found'})
    
    if sale.get('status') == 'CANCELLED':
        return jsonify({'success': False, 'message': 'Bill already cancelled'})
    
    # 1. Return all items to stock
    now = datetime.datetime.now()
    agg = get_aggregated_inventory()
    
    for item in sale['details']:
        if item['qty'] > 0:
            # Find last cost for this product
            p_agg = next((x for x in agg if x['code'] == str(item['id'])), None)
            cost = p_agg['last_cost'] if p_agg else 0.0

            STORAGE.append({
                'batch_id': f"CAN-#{bill_id}-{item['id']}",
                'code': str(item['id']),
                'qty': item['qty'],
                'entry_time': now.strftime("%Y-%m-%d %H:%M:%S"),
                'arrival_date': now.strftime("%Y-%m-%d"),
                'expiry': None,
                'cost': cost,
                'invoice_no': f"CANCEL-#{bill_id}"
            })

    # 2. Add to Returns Log (for the whole bill)
    return_date = now.strftime("%Y-%m-%d %H:%M:%S")
    for item in sale['details']:
        if item['qty'] > 0:
            RETURNS_LOG.append({
                'date': return_date,
                'type': 'BILL_CANCELLATION',
                'bill_id': bill_id,
                'product_code': str(item['id']),
                'product_name': item.get('name', 'Unknown'),
                'qty': item['qty'],
                'refund_amount': item['qty'] * item['price']
            })

    sale['status'] = 'CANCELLED'
    sale['prev_total'] = sale['total']
    sale['total'] = 0
    sale['balance'] = 0 # Clear any debt
    
    # 3. DB Persistence
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('UPDATE sales_log SET status = ?, prev_total = ?, total = ?, balance = ? WHERE id = ?', ('CANCELLED', sale['prev_total'], 0, 0, bill_id))
        
        # Log all items to DB returns_log
        for item in sale['details']:
            if item['qty'] > 0:
                cur.execute('INSERT INTO returns_log (date, product_code, product_name, qty, refund_amount, bill_id, type) VALUES (?, ?, ?, ?, ?, ?, ?)',
                            (return_date, str(item['id']), item.get('name', 'Unknown'), item['qty'], item['qty'] * item['price'], bill_id, 'BILL_CANCELLATION'))
        
        # Update storage (Rewrite table)
        cur.execute('DELETE FROM storage')
        for b in STORAGE:
             cur.execute('INSERT INTO storage (batch_id, product_code, qty, entry_time, arrival_date, expiry, cost, invoice_no, remarks, grade, product_name, unit) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                      (b.get('batch_id'), b.get('code'), b.get('qty', 0), b.get('entry_time'), b.get('arrival_date'), b.get('expiry'), b.get('cost', 0), b.get('invoice_no'), b.get('remarks'), b.get('grade'), b.get('product_name'), b.get('unit')))
             
        # Bulk zero out item quantities in DB and memory
        cur.execute('UPDATE sale_items SET qty = 0 WHERE bill_id = ?', (bill_id,))
        for item in sale['details']:
            item['qty'] = 0
            
        conn.commit()

        # Handle Reprocessing (Moving to Billing for new bill)
        if data.get('reprocess'):
            session['reprocess_cart'] = []
            inv = get_aggregated_inventory()
            for item in sale['details']:
                if item['qty'] > 0:
                    code_str = str(item.get('product_code') or item.get('id', ''))
                    p_m = next((x for x in inv if str(x['code']) == code_str), None)
                    if not p_m:
                        p_m = next((p for p in PRODUCTS if str(p['code']) == code_str), None)
                    
                    r_name = p_m['name'] if p_m else item.get('name', 'Unknown')
                    r_price = float(p_m['price']) if p_m else float(item.get('price', 0))
                    if r_price <= 0:
                        r_price = float(item.get('price', 0))

                    session['reprocess_cart'].append({
                        'id': code_str,
                        'code': code_str,
                        'name': r_name,
                        'price': r_price,
                        'qty': item['qty'],
                        'unit': item.get('unit') or (p_m['unit'] if p_m else 'PCS'),
                        'stock': p_m.get('stock', 999) if p_m and 'stock' in p_m else 999,
                        'grade': p_m.get('grade', 'N/A') if p_m and 'grade' in p_m else 'N/A',
                        'gst_percent': p_m.get('gst_percent', 5) if p_m else 5
                    })
            session.modified = True

        return jsonify({'success': True})
    except Exception as e:
        if conn: conn.rollback()
        return jsonify({'success': False, 'message': str(e)})
    finally:
        if conn: conn.close()


@app.route('/api/inventory/add', methods=['POST'])
def add_inventory():
    if session.get('role') not in ['inventory', 'admin']:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
        
    data = request.json
    try:
        new_prod = {
            'code': data.get('code'),
            'name': data.get('name'),
            'category': data.get('category', 'General'),
            'price': float(data.get('price'))
        }
        if any(p['code'] == new_prod['code'] for p in PRODUCTS):
             return jsonify({'success': False, 'message': 'Product code already exists'})
             
        PRODUCTS.append(new_prod)
        
        initial_stock = int(data.get('stock', 0))
        if initial_stock > 0:
            now = datetime.datetime.now()
            batch_id = f"{now.strftime('%d%m')}-{now.strftime('%H%M%S')}"
            STORAGE.append({
                'batch_id': batch_id,
                'code': new_prod['code'],
                'qty': initial_stock,
                'entry_time': now.strftime("%Y-%m-%d %H:%M:%S"),
                'expiry': None 
            })
        save_data()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/product/<code>')
def get_product(code):
    product = next((item for item in PRODUCTS if item['code'] == code), None)
    if product:
        total_qty = sum(batch['qty'] for batch in STORAGE if batch['code'] == code)
        product_view = product.copy()
        product_view['id'] = code 
        product_view['stock'] = total_qty
        return jsonify({'success': True, 'product': product_view})
    return jsonify({'success': False, 'message': 'Product not found'})


@app.route('/api/product/delete/<code>', methods=['POST'])
def delete_product(code):
    if session.get('role') not in ['inventory', 'admin']:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    global PRODUCTS, STORAGE
    PRODUCTS = [p for p in PRODUCTS if p['code'] != str(code)]
    STORAGE = [b for b in STORAGE if b['code'] != str(code)]
    save_data()
    return jsonify({'success': True})

@app.route('/api/product/edit/<code>', methods=['POST'])
def edit_product(code):
    if session.get('role') not in ['inventory', 'admin']:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    data = request.json
    product = next((p for p in PRODUCTS if p['code'] == str(code)), None)
    if not product:
        return jsonify({'success': False, 'message': 'Product not found'})
    
    product['name'] = data.get('name', product['name'])
    product['name_ta'] = data.get('name_ta', product.get('name_ta', ''))
    product['category'] = data.get('category', product['category'])
    product['price'] = float(data.get('price', product['price']))
    product['is_loose'] = 1 if data.get('is_loose', False) else 0
    product['price_per_gram'] = float(data.get('price_per_gram', product.get('price_per_gram', 0)))
    product['reorder_level'] = int(data.get('reorder_level', product.get('reorder_level', 10)))
    product['gst_percent'] = float(data.get('gst_percent', product.get('gst_percent', 0)))
    product['igst_percent'] = float(data.get('igst_percent', product.get('igst_percent', 0)))
    product['last_cost'] = float(data.get('last_cost', product.get('last_cost', 0)))
    product['wholesale_price'] = float(data.get('wholesale_price', product.get('wholesale_price', 0)))
    
    # DB Persistence
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('''UPDATE products SET name = ?, name_ta = ?, category = ?, price = ?, is_loose = ?, price_per_gram = ?, reorder_level = ?, gst_percent = ?, igst_percent = ?, last_cost = ?, wholesale_price = ?
                       WHERE code = ?''', 
                    (product['name'], product['name_ta'], product['category'], product['price'], product['is_loose'], 
                     product['price_per_gram'], product['reorder_level'], product['gst_percent'], product['igst_percent'], product['last_cost'], product['wholesale_price'], code))
        conn.commit()
    except Exception as e:
        if conn: conn.rollback()
        return jsonify({'success': False, 'message': str(e)})
    finally:
        if conn: conn.close()

    load_data()
    return jsonify({'success': True})

@app.route('/inventory/suppliers')
def suppliers_dashboard():
    if session.get('role') not in ['inventory', 'admin']:
        return redirect(url_for('login'))
    return render_template('inventory/suppliers.html', suppliers=SUPPLIERS)

@app.route('/api/suppliers/delete/<int:id>', methods=['POST'])
def delete_supplier(id):
    if session.get('role') not in ['inventory', 'admin']:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    global SUPPLIERS
    SUPPLIERS = [s for s in SUPPLIERS if s['id'] != id]
    save_data()
    return jsonify({'success': True})

@app.route('/api/suppliers/edit/<int:id>', methods=['POST'])
def edit_supplier(id):
    if session.get('role') not in ['inventory', 'admin']:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    data = request.json
    supplier = next((s for s in SUPPLIERS if s['id'] == id), None)
    if not supplier:
        return jsonify({'success': False, 'message': 'Supplier not found'})
    
    supplier['name'] = data.get('name', supplier['name'])
    supplier['contact'] = data.get('contact', supplier['contact'])
    supplier['phone'] = data.get('phone', supplier['phone'])
    supplier['email'] = data.get('email', supplier['email'])
    save_data()
    return jsonify({'success': True})

@app.route('/api/suppliers/add', methods=['POST'])
def add_supplier():
    if session.get('role') not in ['inventory', 'admin']:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
        
    data = request.json
    try:
        SUPPLIERS.append({
            'id': len(SUPPLIERS) + 1,
            'name': data.get('name'),
            'contact': data.get('contact'),
            'phone': data.get('phone'),
            'email': data.get('email')
        })
        save_data()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/inventory/returns')
def inventory_returns():
    if session.get('role') not in ['inventory', 'admin']:
        return redirect(url_for('login'))
    return render_template('inventory/returns.html', returns=RETURNS_LOG)

@app.route('/inventory/accounts')
def inventory_accounts():
    if session.get('role') not in ['inventory', 'admin']:
        return redirect(url_for('login'))
    return render_template('inventory/accounts.html')

@app.route('/api/inventory/return', methods=['POST'])
def process_return():
    if session.get('role') not in ['inventory', 'admin']:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    data = request.json
    code = data.get('code')
    qty = int(data.get('qty', 0))
    action = data.get('action') 
    reason = data.get('reason')
    
    product = next((p for p in PRODUCTS if p['code'] == code), None)
    if not product:
        return jsonify({'success': False, 'message': 'Product not found'})
        
    global STORAGE
    if action == 'scrap':
        required = qty
        available = sum(b['qty'] for b in STORAGE if b['code'] == code)
        if available < required:
             return jsonify({'success': False, 'message': 'Insufficient stock to scrap'})
             
        product_batches = sorted([b for b in STORAGE if b['code'] == code], key=lambda x: x['entry_time'])
        for batch in product_batches:
            if required <= 0: break
            if batch['qty'] >= required:
                batch['qty'] -= required
                required = 0
            else:
                required -= batch['qty']
                batch['qty'] = 0
        STORAGE = [b for b in STORAGE if b['qty'] > 0]
        
    elif action == 'restock':
        now = datetime.datetime.now()
        batch_id = f"RET-{now.strftime('%j%H%M')}"
        STORAGE.append({
            'batch_id': batch_id,
            'code': code,
            'qty': qty,
            'entry_time': now.strftime("%Y-%m-%d %H:%M:%S"),
            'expiry': None 
        })

    # DB Persistence
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Log return
        ret_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # Ensure returns_log table has the expected schema if missing
        try:
            cur.execute('INSERT INTO returns_log (date, product_code, product_name, qty, reason, action) VALUES (?, ?, ?, ?, ?, ?)',
                        (ret_date, code, product['name'], qty, reason, action))
        except sqlite3.OperationalError:
            # Fallback for different schema if necessary
            pass
    
        # Update storage
        cur.execute('DELETE FROM storage')
        for b in STORAGE:
             cur.execute('INSERT INTO storage (batch_id, product_code, qty, entry_time, arrival_date, expiry, cost, invoice_no, remarks, grade, product_name, unit) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                      (b.get('batch_id'), b.get('code'), b.get('qty', 0), b.get('entry_time'), b.get('arrival_date'), b.get('expiry'), b.get('cost', 0), b.get('invoice_no'), b.get('remarks'), b.get('grade'), b.get('product_name'), b.get('unit')))
        
        conn.commit()
    except Exception as e:
        if conn: conn.rollback()
        return jsonify({'success': False, 'message': str(e)})
    finally:
        if conn: conn.close()

    RETURNS_LOG.append({
        'date': ret_date,
        'product_code': code,
        'product_name': product['name'],
        'qty': qty,
        'reason': reason,
        'action': action
    })
    return jsonify({'success': True})

def send_fast2sms(mobile, message):
    """Generic helper to send SMS via Fast2SMS"""
    # --- CONFIGURATION ---
    API_KEY = "YOUR_API_KEY_HERE" 
    URL = "https://www.fast2sms.com/dev/bulkV2"
    
    if API_KEY == "YOUR_API_KEY_HERE":
        print(f"\n[SMS SKIPPED] Real SMS requires API Key. To: {mobile} | Msg: {message}\n")
        return False

    try:
        import requests
        payload = {
            "route": "q",
            "message": message,
            "language": "english",
            "flash": 0,
            "numbers": mobile
        }
        headers = {
            "authorization": API_KEY,
            "Content-Type": "application/json"
        }
        response = requests.post(URL, json=payload, headers=headers)
        print(f"\n[SMS API] Sent to {mobile}. Response: {response.text}\n")
        return response.status_code == 200
    except Exception as e:
        print(f"SMS API Error: {str(e)}")
        return False

def send_offer_sms(mobile, name, amount):
    msg = f"Dear {name if name else 'Customer'}, Thanks for shopping at Maple Pro! Bill Amt: {amount}. See you soon!"
    return send_fast2sms(mobile, msg)

@app.route('/billing/customers')
def billing_customers():
    if session.get('role') not in ['sales', 'admin']:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    cur = conn.cursor()
    # Group by customer and calculate total balance
    cur.execute('''
        SELECT 
            customer_mobile as customer_mobile,
            MAX(customer_name) as customer_name,
            MAX(customer_id) as customer_id,
            SUM(balance) as total_balance
        FROM sales_log 
        WHERE ((customer_mobile IS NOT NULL AND customer_mobile != "")
           OR (customer_id IS NOT NULL AND customer_id != "")
           OR (customer_name IS NOT NULL AND customer_name != ""))
           AND payment_method = 'CREDIT'
        GROUP BY 
            CASE 
                WHEN customer_mobile IS NOT NULL AND customer_mobile != "" THEN customer_mobile 
                ELSE customer_name 
            END
        ORDER BY total_balance DESC, customer_name ASC
    ''')
    customers = [dict(row) for row in cur.fetchall()]
    
    cur.execute('SELECT SUM(balance) as total FROM sales_log WHERE payment_method = "CREDIT"')
    res = cur.fetchone()
    grand_total_owed = res['total'] if res and res['total'] else 0.0
    
    conn.close()
    
    return render_template('billing/customers.html', customers=customers, grand_total_owed=grand_total_owed, page='customers')

@app.route('/billing/reports/customer-ledger')
def report_customer_ledger():
    if session.get('role') not in ['sales', 'admin']: return redirect(url_for('login'))
    
    mobile = request.args.get('mobile')
    cid = request.args.get('id')
    if not mobile and not cid:
        return redirect(url_for('billing_customers'))
    
    # Filter sales by customer_id (priority) or customer_mobile
    if cid:
        customer_sales = [s for s in SALES_LOG if str(s.get('customer_id')) == str(cid)]
    else:
        customer_sales = [s for s in SALES_LOG if s.get('customer_mobile') == mobile]
        
    enriched = enrich_sales_data(customer_sales)
    
    # Get customer name
    customer_name = request.args.get('name', 'Customer')
    if enriched:
        customer_name = enriched[-1].get('customer_name', customer_name)
    
    return render_template('billing/customer_ledger.html', 
                           title='Customer Statement', 
                           data=enriched, 
                           customer_name=customer_name, 
                           customer_mobile=mobile or 'N/A',
                           customer_id=cid or 'N/A')

@app.route('/api/billing/broadcast', methods=['POST'])
def broadcast_offer():
    if session.get('role') not in ['sales', 'admin']:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    data = request.json
    custom_message = data.get('message')
    if not custom_message:
        return jsonify({'success': False, 'message': 'Message cannot be empty'})

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT DISTINCT customer_mobile, customer_name FROM sales_log WHERE customer_mobile IS NOT NULL AND customer_mobile != ""')
    targets = cur.fetchall()
    conn.close()

    if not targets:
        return jsonify({'success': False, 'message': 'No customers with mobile numbers found'})

    def run_broadcast(recipient_list, msg):
        for t in recipient_list:
            # We can personalize if needed, but the user asked for custom message
            # If they want personalization, they can use codes like {name}
            final_msg = msg.replace("{name}", t['customer_name'] if t['customer_name'] else "Customer")
            send_fast2sms(t['customer_mobile'], final_msg)

    threading.Thread(target=run_broadcast, args=(targets, custom_message)).start()
    
    return jsonify({'success': True, 'count': len(targets)})

@app.route('/api/checkout', methods=['POST'])
def checkout():
    global STORAGE, SALES_LOG
    try:
        data = request.json or {}
        cart = data.get('cart', [])
        
        # Robust Financial Parsing
        total = float(data.get('total', 0) or 0)          # Handle None with or 0
        gross_total = float(data.get('gross_total', total) or total) 
        discount = float(data.get('discount', 0) or 0)
        
        payment_method = data.get('payment_method', 'CASH').upper()
        
        # Handle Complimentary Mode
        if payment_method == 'COMPLIMENT':
            total = 0.0
            gross_total = 0.0
            discount = 0.0
            # Zero out individual item prices to ensure reports show 0 revenue
            for item in cart:
                item['price'] = 0.0
                item['gst_percent'] = 0.0
                item['igst_percent'] = 0.0
        
        # Customer Details
        customer_name = data.get('customer_name', '') or 'Walk-in'
        customer_mobile = data.get('customer_mobile', '')
        customer_id = data.get('customer_id', '')
        amount_paid_raw = data.get('amount_paid', 0)
        amount_paid = float(amount_paid_raw if amount_paid_raw is not None else 0)
        send_sms = data.get('send_offer_sms', False)
        
        # Calculate Balance
        balance = 0.0
        if payment_method == 'CREDIT':
            balance = total - amount_paid
        else:
            amount_paid = total # Full payment for non-credit
            balance = 0.0

        # Check if this is a Correction Bill
        bill_status = 'ACTIVE'
        source_bill_id = session.pop('source_bill_id', None)
        if session.pop('is_correction', False):
            bill_status = 'CORRECTION'

        if not cart:
            return jsonify({'success': False, 'message': 'Cart is empty'})

        # Stock Check
        for item in cart:
            required = item['qty']
            available = sum(b['qty'] for b in STORAGE if b['code'] == str(item['code']))
            if available < required:
                 return jsonify({'success': False, 'message': f"Insufficient stock for {item['name']}"})
        
        # Stock Deduction (FIFO)
        for item in cart:
            code = str(item['code'])
            required = item['qty']
            product_batches = sorted([b for b in STORAGE if b['code'] == code], key=lambda x: x['entry_time'])
            for batch in product_batches:
                if required <= 0: break
                if batch['qty'] >= required:
                    batch['qty'] -= required
                    required = 0
                else:
                    required -= batch['qty']
                    batch['qty'] = 0
                    
        STORAGE = [b for b in STORAGE if b['qty'] > 0]

        # Insert Sale into DB
        conn = get_db_connection()
        cur = conn.cursor()
        
        sale_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        cur.execute('''INSERT INTO sales_log 
            (date, items_count, total, payment_method, status, customer_name, customer_mobile, customer_id, amount_paid, balance, discount, gross_total, source_bill_id) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (sale_date, len(cart), total, payment_method, bill_status, customer_name, customer_mobile, customer_id, amount_paid, balance, discount, gross_total, source_bill_id))
            
        sale_id = cur.lastrowid
        
        # Update Storage DB (Stock Deduction)
        cur.execute('DELETE FROM storage')
        for b in STORAGE:
             cur.execute('INSERT INTO storage (batch_id, product_code, qty, entry_time, arrival_date, expiry, cost, invoice_no, remarks, grade, product_name, unit) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                      (b.get('batch_id'), b.get('code'), b.get('qty', 0), b.get('entry_time'), b.get('arrival_date'), b.get('expiry'), b.get('cost', 0), b.get('invoice_no'), b.get('remarks'), b.get('grade'), b.get('product_name'), b.get('unit')))
    
        # Insert Sale Items
        for item in cart:
            cur.execute('INSERT INTO sale_items (bill_id, product_code, product_name, product_name_ta, category, price, qty, bizz, gst_percent, igst_percent) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                        (sale_id, str(item['code']), item['name'], item.get('name_ta', ''), item.get('category', ''), item['price'], item['qty'], item.get('bizz', 0), item.get('gst_percent', 0), item.get('igst_percent', 0)))
                        
        conn.commit()
        
        sale_record = {
            'id': sale_id,
            'date': sale_date,
            'items': len(cart),
            'total': total,
            'gross_total': gross_total,
            'discount': discount,
            'payment_method': payment_method,
            'customer_name': customer_name,
            'customer_mobile': customer_mobile,
            'customer_id': customer_id,
            'amount_paid': amount_paid,
            'balance': balance,
            'details': cart,
            'status': bill_status,
            'source_bill_id': source_bill_id
        }
        SALES_LOG.append(sale_record)
        return jsonify({'success': True, 'sale_id': sale_id})

    except Exception as e:
        if 'conn' in locals() and conn: conn.rollback()
        return jsonify({'success': False, 'message': f"Checkout Error: {str(e)}"})
    finally:
        if 'conn' in locals() and conn: conn.close()

    return jsonify({'success': True, 'sale_id': sale_id})


# --- Admin Data Manager Routes ---
@app.route('/admin/db')
def admin_db():
    if session.get('role') not in ['inventory', 'admin']: 
        return redirect(url_for('login'))
    return render_template('admin_db.html')

@app.route('/admin/db/query', methods=['POST'])
def admin_db_query():
    if session.get('role') not in ['inventory', 'admin']:
        return redirect(url_for('login'))
        
    query = request.form.get('query')
    conn = get_db_connection()
    result = []
    columns = []
    error = None
    
    try:
        cursor = conn.execute(query)
        if query.strip().upper().startswith('SELECT'):
            result = [dict(row) for row in cursor.fetchall()]
            if result:
                columns = list(result[0].keys())
        else:
            conn.commit()
            result = [{'Status': 'Query Executed Successfully', 'Rows Affected': cursor.rowcount}]
            columns = ['Status', 'Rows Affected']
            load_data() # Refresh cache
    except Exception as e:
        error = str(e)
    finally:
        conn.close()
        
    return render_template('admin_db.html', result=result, columns=columns, error=error)

@app.route('/admin/db/view/<table>')
def admin_db_view_table(table):
    if session.get('role') not in ['inventory', 'admin']:
        return redirect(url_for('login'))
        
    conn = get_db_connection()
    try:
        rows = conn.execute(f'SELECT * FROM {table}').fetchall()
        result = [dict(row) for row in rows]
        columns = list(result[0].keys()) if result else []
    except Exception as e:
        return f"Error: {e}"
    conn.close()
    return render_template('admin_db.html', result=result, columns=columns)

@app.route('/admin/reset-data')
def admin_reset_data():
    if session.get('role') not in ['inventory', 'admin']:
        return redirect(url_for('login'))
        
    conn = get_db_connection()
    try:
        # Drop all tables
        tables = ['products', 'suppliers', 'storage', 'sales_log', 'sale_items', 'returns_log']
        for table in tables:
            conn.execute(f'DROP TABLE IF EXISTS {table}')
            
        # Re-create tables manually (copying schema from database_setup.py for safety/speed)
        # Products
        conn.execute('''CREATE TABLE products (
            code TEXT PRIMARY KEY,
            name TEXT,
            name_ta TEXT,
            category TEXT,
            price REAL,
            price_per_gram REAL DEFAULT 0,
            unit TEXT DEFAULT 'PCS',
            bizz REAL DEFAULT 0,
            is_loose INTEGER DEFAULT 0,
            reorder_level INTEGER DEFAULT 10,
            last_cost REAL DEFAULT 0,
            gst_percent REAL DEFAULT 0,
            igst_percent REAL DEFAULT 0,
            wholesale_price REAL DEFAULT 0
        )''')
        # Suppliers
        conn.execute('''CREATE TABLE suppliers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            contact TEXT,
            phone TEXT,
            email TEXT,
            balance REAL DEFAULT 0
        )''')
        # Seed default supplier
        conn.execute("INSERT INTO suppliers (name, contact, phone, email, balance) VALUES ('General Vendor', 'N/A', '-', '-', 0)")
        # Storage                                                                               
        conn.execute('''CREATE TABLE storage (
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
        # Sales Log
        conn.execute('''CREATE TABLE sales_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            items_count INTEGER,
            total REAL,
            payment_method TEXT,
            status TEXT DEFAULT 'ACTIVE',
            prev_total REAL DEFAULT 0
        )''')
        # Sale Items
        conn.execute('''CREATE TABLE sale_items (
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
        # Returns Log
        conn.execute('''CREATE TABLE returns_log (
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
        load_data() # Clear RAM
        return "System has been reset successfully. <a href='/inventory'>Go to Dashboard</a>"
    except Exception as e:
        return f"Reset Failed: {e}"
    finally:
        conn.close()

@app.route('/inventory/stock-return')
def inventory_stock_return():
    if session.get('role') not in ['inventory', 'admin']:
        return redirect(url_for('login'))
    
    inventory = get_aggregated_inventory()
    # Sort logs by date descending
    logs = sorted(RETURNS_LOG, key=lambda x: x['date'], reverse=True)
    
    return render_template('inventory/stock_return.html', inventory=inventory, logs=logs, page='stock_return')

@app.route('/api/inventory/return-stock', methods=['POST'])
def api_return_stock():
    data = request.json
    p_code = data.get('product_code')
    qty = float(data.get('qty', 0))
    reason = data.get('reason')
    notes = data.get('notes', '')
    batch_id = data.get('batch_id')
    
    if not p_code or qty <= 0:
        return jsonify({'success': False, 'message': 'Invalid data'})
        
    conn = get_db_connection()
    
    try:
        cost = 0
        # 1. Deduct Stock
        if batch_id:
            # Deduct from specific batch
            batch = conn.execute('SELECT * FROM storage WHERE batch_id = ?', (batch_id,)).fetchone()
            if not batch:
                 return jsonify({'success': False, 'message': 'Batch not found'})
            
            if batch['qty'] < qty:
                 return jsonify({'success': False, 'message': f"Insufficient batch stock (Available: {batch['qty']})"})
            
            new_qty = batch['qty'] - qty
            conn.execute('UPDATE storage SET qty = ? WHERE id = ?', (new_qty, batch['id']))
            cost = batch['cost']
        else:
            # FIFO Deduction
            batches = conn.execute('SELECT * FROM storage WHERE product_code = ? AND qty > 0 ORDER BY entry_time', (p_code,)).fetchall()
            
            # Check total stock first
            total_stock = sum(b['qty'] for b in batches)
            if total_stock < qty:
                 return jsonify({'success': False, 'message': f"Insufficient stock (Available: {total_stock})"})

            remaining = qty
            total_value = 0
            
            for b in batches:
                if remaining <= 0: break
                
                deduct = min(b['qty'], remaining)
                new_qty = b['qty'] - deduct
                conn.execute('UPDATE storage SET qty = ? WHERE id = ?', (new_qty, b['id']))
                
                total_value += (deduct * b['cost'])
                remaining -= deduct
            
            # Avg cost for log
            cost = total_value / qty if qty > 0 else 0

        # 2. Log Return
        prod = conn.execute('SELECT name FROM products WHERE code = ?', (p_code,)).fetchone()
        p_name = prod['name'] if prod else 'Unknown'
        
        date_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        conn.execute('INSERT INTO returns_log (date, type, product_code, product_name, qty, refund_amount) VALUES (?, ?, ?, ?, ?, ?)',
                     (date_str, reason, p_code, p_name, qty, cost * qty))
        
        conn.commit()
        load_data() # Refresh cache
        return jsonify({'success': True})
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})
    finally:
        conn.close()


@app.route('/api/billing/prepare-reprocess', methods=['POST'])
def prepare_reprocess():
    if session.get('role') not in ['sales', 'admin']:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    
    data = request.json
    bill_id = data.get('bill_id')
    return_item_id = str(data.get('item_id'))
    qty_to_return = float(data.get('qty', 0))
    
    sale = next((s for s in SALES_LOG if s['id'] == bill_id), None)
    if not sale: return jsonify({'success': False, 'message': 'Bill not found'})
    
    if sale.get('status') == 'CANCELLED':
        return jsonify({'success': False, 'message': 'Bill is already cancelled'})

    # 1. Restock the RETURNED quantity
    now = datetime.datetime.now()
    agg = get_aggregated_inventory()
    p_agg = next((x for x in agg if x['code'] == return_item_id), None)
    cost = p_agg['last_cost'] if p_agg else 0.0

    STORAGE.append({
        'batch_id': f"REPROC-#{bill_id}",
        'code': return_item_id,
        'qty': qty_to_return,
        'entry_time': now.strftime("%Y-%m-%d %H:%M:%S"),
        'arrival_date': now.strftime("%Y-%m-%d"),
        'expiry': None,
        'cost': cost,
        'invoice_no': f"RETURN-REPROC-#{bill_id}"
    })

    # 2. Add to Returns Log
    return_date = now.strftime("%Y-%m-%d %H:%M:%S")
    p_code_field = 'product_code' if 'product_code' in sale['details'][0] else 'id'
    item_in_bill = next((i for i in sale['details'] if str(i.get(p_code_field)) == return_item_id), None)
    
    if not item_in_bill:
        return jsonify({'success': False, 'message': 'Item not found in this bill'})

    item_name = item_in_bill.get('name') or item_in_bill.get('product_name') or 'Unknown'
    item_price = item_in_bill.get('price', 0)

    RETURNS_LOG.append({
        'date': return_date,
        'type': 'REPROCESS_RETURN',
        'bill_id': bill_id,
        'product_code': return_item_id,
        'product_name': item_name,
        'qty': qty_to_return,
        'refund_amount': qty_to_return * item_price
    })

    # 3. Create the "Remaining items" cart for POS
    new_cart = []
    for item in sale['details']:
        item_code = str(item.get('product_code') or item.get('id'))
        rem_qty = item['qty']
        
        if item_code == return_item_id:
            rem_qty -= qty_to_return
        
        if rem_qty > 0:
            prod = next((p for p in agg if p['code'] == item_code), None)
            if prod:
                new_cart.append({
                    'code': prod['code'],
                    'name': prod['name'],
                    'category': prod['category'],
                    'price': prod['price'],
                    'stock': prod['stock'], 
                    'unit': prod.get('unit', 'PCS'),
                    'qty': rem_qty,
                    'gross_amount': rem_qty * prod['price']
                })

    # 4. Mark old bill as RETURNED (Archive state)
    sale['status'] = 'RETURNED'
    sale['total'] = 0
    sale['balance'] = 0

    # DB Persistence
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('UPDATE sales_log SET status = ?, total = 0, balance = 0 WHERE id = ?', ('RETURNED', bill_id))
        cur.execute('INSERT INTO returns_log (date, product_code, product_name, qty, refund_amount, bill_id, type) VALUES (?, ?, ?, ?, ?, ?, ?)',
                    (return_date, return_item_id, item_name, qty_to_return, qty_to_return * item_price, bill_id, 'REPROCESS_RETURN'))

        cur.execute('DELETE FROM storage')
        for b in STORAGE:
             cur.execute('INSERT INTO storage (batch_id, product_code, qty, entry_time, arrival_date, expiry, cost, invoice_no, remarks, grade, product_name, unit) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                      (b.get('batch_id'), b.get('code'), b.get('qty', 0), b.get('entry_time'), b.get('arrival_date'), b.get('expiry'), b.get('cost', 0), b.get('invoice_no'), b.get('remarks'), b.get('grade'), b.get('product_name'), b.get('unit')))
        conn.commit()
    except Exception as e:
        if conn: conn.rollback()
        return jsonify({'success': False, 'message': f"DB Error: {str(e)}"})
    finally:
        if conn: conn.close()

    session['reprocess_cart'] = new_cart
    session['is_correction'] = True # Set flag for next bill
    session['source_bill_id'] = bill_id # Track origin
    return jsonify({'success': True, 'redirect': '/billing'})

def run_flask():
    # Only run the server here
    try:
        serve(app, host="0.0.0.0", port=5003)
    except Exception:
        app.run(port=5005)

@app.route('/api/customer/<string:cust_id>')
def get_customer(cust_id):
    conn = get_db_connection()
    cur = conn.cursor()
    # Search for the most recent transaction with this customer_id
    cur.execute('SELECT customer_name, customer_mobile FROM sales_log WHERE customer_id = ? AND customer_name != "Walk-in" ORDER BY id DESC LIMIT 1', (cust_id,))
    row = cur.fetchone()
    conn.close()
    
    if row:
        return jsonify({
            'success': True,
            'name': row['customer_name'],
            'mobile': row['customer_mobile']
        })
    return jsonify({'success': False, 'message': 'Customer not found'})

def get_practice_showcase_data():
    return {
        'hero_stats': [
            {'label': 'Practice Problems', 'value': '150+'},
            {'label': 'Mock Contests', 'value': '24'},
            {'label': 'Success Rate', 'value': '92%'}
        ],
        'tracks': [
            {
                'title': 'Beginner Path',
                'description': 'Learn arrays, strings, loops, and functions with guided hints.',
                'level': 'Easy',
                'lessons': 18
            },
            {
                'title': 'Interview Sprint',
                'description': 'Sharpen problem solving with stacks, queues, recursion, and search.',
                'level': 'Medium',
                'lessons': 26
            },
            {
                'title': 'Contest Arena',
                'description': 'Prepare for timed rounds with dynamic programming and graph challenges.',
                'level': 'Advanced',
                'lessons': 14
            }
        ],
        'problems': [
            {'title': 'Two Sum', 'difficulty': 'Easy', 'tags': ['Array', 'Hash Map'], 'solved': 1280},
            {'title': 'Valid Parentheses', 'difficulty': 'Easy', 'tags': ['Stack'], 'solved': 990},
            {'title': 'Longest Substring Without Repeating Characters', 'difficulty': 'Medium', 'tags': ['String', 'Sliding Window'], 'solved': 740},
            {'title': 'Merge Intervals', 'difficulty': 'Medium', 'tags': ['Sorting'], 'solved': 610},
            {'title': 'Word Ladder', 'difficulty': 'Hard', 'tags': ['Graph', 'BFS'], 'solved': 240}
        ],
        'features': [
            {
                'title': 'Live Code Playground',
                'description': 'Write solutions, test sample input, and review output instantly.'
            },
            {
                'title': 'Progress Analytics',
                'description': 'Track solved problems, streaks, and topic-wise performance.'
            },
            {
                'title': 'Company Focus Sets',
                'description': 'Practice curated question lists for placement and interview preparation.'
            }
        ]
    }

@app.route('/api/practice-data')
def practice_data_api():
    return jsonify(get_practice_showcase_data())

@app.route('/submission')
def submission_redirect():
    return redirect(url_for('online_coding_practice'))

@app.route('/online-coding-practice')
def online_coding_practice():
    practice_data = get_practice_showcase_data()
    return render_template('online_coding_practice.html', practice_data=practice_data)

if __name__ == '__main__':
    # 1. Start Flask in background thread
    print("Starting server on port 5003...")
    threading.Thread(target=run_flask, daemon=True).start()

    # Small delay to ensure server starts
    import time
    time.sleep(2)

    try:
        # 2. Start the Desktop Window
        print("Launching Desktop Window...")
        webview.create_window(
            "Jai Agency",
            "http://127.0.0.1:5003/",
            width=1200,
            height=800
        )
        webview.start()
    except (NameError, Exception) as e:
        print(f"Webview failed or not installed: {e}")
        print("Falling back to browser mode...")
        webbrowser.open_new('http://127.0.0.1:5003/')
        # Keep the main thread alive if webview isn't running
        while True:
            time.sleep(1)
