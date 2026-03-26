import sqlite3

import smtplib

import os

import sys

from datetime import datetime

from email.mime.text import MIMEText

from email.mime.multipart import MIMEMultipart

from email.mime.application import MIMEApplication

from fpdf import FPDF



# -------------------------------------------------

# âœ… CONFIGURATION

# -------------------------------------------------

FACTORY_NAME = "Jai Agency"



def get_db_path():
    # 1. Target ProgramData path
    program_data = os.environ.get('ProgramData', 'C:\\ProgramData')
    jai_data_dir = os.path.join(program_data, 'jai agency')
    
    target_db = os.path.join(jai_data_dir, 'JAI_AGENCY.db')
    if os.path.exists(target_db):
        return target_db
        
    # Fallback to local
    if getattr(sys, 'frozen', False):
        base_dir = os.path.dirname(sys.executable)
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))
    
    return os.path.join(base_dir, 'JAI_AGENCY.db')



DATABASE = get_db_path()



def get_db():

    if not os.path.exists(DATABASE):

        return None

    conn = sqlite3.connect(DATABASE)

    conn.row_factory = sqlite3.Row

    return conn



# -----------------------------

# FETCH TODAY'S REPORT DATA

# -----------------------------

def get_report_data():

    conn = get_db()

    if not conn:

        return None



    cur = conn.cursor()

    data = {}

    today_str = datetime.now().strftime('%Y-%m-%d')

    

    # 1. Today's Sales (Invoices)

    cur.execute("""

        SELECT id, customer_name, total, payment_method, date 

        FROM sales_log 

        WHERE date LIKE ? AND status = 'ACTIVE'

    """, (f"{today_str}%",))

    data['sales'] = [dict(row) for row in cur.fetchall()]

    

    cur.execute("""

        SELECT SUM(total) as total 

        FROM sales_log 

        WHERE date LIKE ? AND status = 'ACTIVE'

    """, (f"{today_str}%",))

    data['total_sales_value'] = cur.fetchone()['total'] or 0

    

    # 2. Stock Inward (Stock Received Today)

    cur.execute("""

        SELECT storage.batch_id, products.name, storage.qty, products.unit 

        FROM storage 

        JOIN products ON storage.product_code = products.code

        WHERE storage.arrival_date = ?

    """, (today_str,))

    data['stock_inward'] = [dict(row) for row in cur.fetchall()]

    

    # 3. Today's Expenses

    cur.execute("""

        SELECT description, amount, category 

        FROM expenses 

        WHERE date LIKE ?

    """, (f"{today_str}%",))

    data['expenses'] = [dict(row) for row in cur.fetchall()]

    

    cur.execute("""

        SELECT SUM(amount) as total 

        FROM expenses 

        WHERE date LIKE ?

    """, (f"{today_str}%",))

    data['total_expenses'] = cur.fetchone()['total'] or 0



    conn.close()

    return data



# -----------------------------

# CLEAN TEXT FOR PDF

# -----------------------------

def clean_for_pdf(text):

    REPLACE = {

        "â€”": "-", "â€“": "-",

        "â€œ": '"', "â€": '"',

        "â€˜": "'", "â€™": "'",

        "â€¢": "-", "â—": "-",

        "\u20B9": "Rs."

    }

    for bad, good in REPLACE.items():

        text = text.replace(bad, good)

    return "".join(ch for ch in text if ord(ch) <= 0xFFFF)



# -----------------------------

# REPORT SUMMARY GENERATION

# -----------------------------

def generate_report_summary():

    data = get_report_data()

    if not data:

        return "Error: Database not found or no data available."



    date_str = datetime.now().strftime("%d %B %Y")

    today = datetime.now().strftime('%d-%m-%Y')

    

    summary = f"{FACTORY_NAME} - DAILY OPERATIONS REPORT ({date_str})\n"

    summary += "="*60 + "\n\n"



    # --- 1. OVERVIEW ---

    summary += f"ACTIVITY SUMMARY FOR: {today}\n"

    summary += f"â€¢ Sales Transactions: {len(data['sales'])}\n"

    summary += f"â€¢ Total Revenue: Rs.{data['total_sales_value']:.2f}\n"

    summary += f"â€¢ Total Expenses Today: Rs.{data['total_expenses']:.2f}\n"

    summary += f"â€¢ Stock Inward Batches: {len(data['stock_inward'])}\n\n"



    # --- 2. SALES DETAILS ---

    summary += "1. TODAY'S SALES LOG:\n" + "-"*30 + "\n"

    if data['sales']:

        for sale in data['sales']:

            summary += f"â€¢ Bill #{sale['id']} | {sale['customer_name']} | Rs.{sale['total']} ({sale['payment_method']})\n"

    else:

        summary += "No sales recorded today.\n"

    summary += "\n"



    # --- 3. STOCK INWARD ---

    summary += "2. TODAY'S STOCK RECEIPTS:\n" + "-"*30 + "\n"

    if data['stock_inward']:

        for item in data['stock_inward']:

            summary += f"â€¢ Batch: {item['batch_id']} | {item['name']} | Qty: {item['qty']} {item['unit']}\n"

    else:

        summary += "No stock arrivals recorded today.\n"

    summary += "\n"



    # --- 4. EXPENSES ---

    summary += "3. TODAY'S EXPENSES:\n" + "-"*30 + "\n"

    if data['expenses']:

        for exp in data['expenses']:

            summary += f"â€¢ {exp['description']} | Rs.{exp['amount']} [{exp['category']}]\n"

    else:

        summary += "No expenses recorded today.\n"

    summary += "\n"



    summary += "\n" + "="*60 + "\n"

    summary += "END OF DAILY OPERATIONS REPORT\n"

    

    return summary



# -----------------------------

# CREATE PDF

# -----------------------------

def create_pdf(summary_text):

    # Determine base directory

    if getattr(sys, 'frozen', False):

        base_dir = os.path.dirname(sys.executable)

    else:

        base_dir = os.path.dirname(os.path.abspath(__file__))

        

    REPORT_DIR = os.path.join(base_dir, "reports")

    os.makedirs(REPORT_DIR, exist_ok=True)



    pdf = FPDF()

    pdf.set_auto_page_break(auto=True, margin=15)

    pdf.add_page()



    # Header

    pdf.set_font("Arial", 'B', size=16)

    pdf.set_text_color(12, 41, 75)

    pdf.cell(0, 15, f"{FACTORY_NAME} - Daily Report", ln=True, align="C")

    pdf.line(20, 25, 190, 25)

    pdf.ln(10)



    # Content

    pdf.set_text_color(0, 0, 0)

    pdf.set_font("Arial", size=10)

    pdf.multi_cell(0, 6, clean_for_pdf(summary_text))



    filename = os.path.join(

        REPORT_DIR,

        f"Daily_Report_{datetime.now().strftime('%Y%j_%H%M')}.pdf"

    )

    pdf.output(filename)

    return filename



# -----------------------------

# SEND EMAIL

# -----------------------------

def send_report_email():

    summary = generate_report_summary()

    

    sender = "maplepro2323@gmail.com"

    password = "vkah llvc mduj yfze"

    receiver = "mfouzhan@gmail.com"



    msg = MIMEMultipart()

    msg["Subject"] = f"{FACTORY_NAME} Report - {datetime.now().strftime('%d %b %Y')}"

    msg["From"] = f"{FACTORY_NAME} MMS <{sender}>"

    msg["To"] = receiver



    # Attach Plain Text version

    msg.attach(MIMEText(summary, "plain"))



    # Create and attach PDF

    pdf_file = None

    try:

        pdf_file = create_pdf(summary)

        with open(pdf_file, "rb") as f:

            part = MIMEApplication(f.read(), _subtype="pdf")

            part.add_header(

                "Content-Disposition",

                "attachment",

                filename=os.path.basename(pdf_file)

            )

            msg.attach(part)

    except Exception as e:

        print(f"[WARNING] PDF Creation failed: {e}")



    # Send

    try:

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:

            server.login(sender, password)

            server.send_message(msg)

        return True, "Email sent successfully with PDF attachment."

    except Exception as e:

        return False, f"Failed to send email: {str(e)}"

