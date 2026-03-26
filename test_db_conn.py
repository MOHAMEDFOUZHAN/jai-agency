import sqlite3
import os
print("Importing app parts...")
from app import get_db_path, DB_FILE
print(f"DB Path: {DB_FILE}")
print("Connecting to DB...")
conn = sqlite3.connect(DB_FILE)
print("Connected.")
cursor = conn.cursor()
print("Getting tables...")
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
print(f"Tables: {cursor.fetchall()}")
conn.close()
print("Done.")
