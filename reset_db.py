import sqlite3
import os

db_path = 'KOKKALATTY.db'

if not os.path.exists(db_path):
    print(f"{db_path} not found.")
else:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    
    # Get all table names
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
    tables = [row[0] for row in cur.fetchall()]
    
    print(f"Tables found: {tables}")
    
    for table in tables:
        try:
            cur.execute(f"DELETE FROM {table};")
            # Reset auto-increment counters
            cur.execute("DELETE FROM sqlite_sequence WHERE name=?;", (table,))
            print(f"Cleared table: {table}")
        except Exception as e:
            print(f"Error clearing {table}: {e}")
            
    conn.commit()
    conn.close()
    print("\nDatabase reset complete. All data has been deleted.")
