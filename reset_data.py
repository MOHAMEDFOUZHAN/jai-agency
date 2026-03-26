import os
import shutil
import database_setup

DB_FILE = 'KOKKALATTY.db'
DATA_FILE = 'data.json'
BACKUP_DATA_FILE = 'data_backup.json'

def reset_application_data():
    print("WARNING: This will delete all current data.")
    
    # 1. Remove the SQLite Database
    if os.path.exists(DB_FILE):
        try:
            os.remove(DB_FILE)
            print(f"Deleted existing database: {DB_FILE}")
        except PermissionError:
            print(f"Error: Could not delete {DB_FILE}. It might be in use. Please stop the Flask app first.")
            return
    else:
        print("No database file found to delete.")

    # 2. Rename data.json to prevent re-importing old data
    if os.path.exists(DATA_FILE):
        if os.path.exists(BACKUP_DATA_FILE):
            os.remove(BACKUP_DATA_FILE) # Remove old backup if exists
        os.rename(DATA_FILE, BACKUP_DATA_FILE)
        print(f"Archived existing data.json to {BACKUP_DATA_FILE}")
    
    # 3. Initialize fresh database
    print("Initializing fresh database schema...")
    database_setup.init_db()
    
    print("\nSUCCESS: System has been reset. You can now start fresh.")

if __name__ == "__main__":
    reset_application_data()
