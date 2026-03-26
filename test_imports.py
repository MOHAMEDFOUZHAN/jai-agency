print("Testing granular imports...")
import os
print("Imported os")
import sys
print("Imported sys")
import threading
print("Imported threading")
import sqlite3
print("Imported sqlite3")
import datetime
print("Imported datetime")
from flask import Flask
print("Imported Flask")
try:
    print("Attempting to import webview...")
    import webview
    print("Imported webview")
    from waitress import serve
    print("Imported waitress")
except Exception as e:
    print(f"Import failed: {e}")
print("Testing get_db_path logic...")
base_dir = os.path.dirname(os.path.abspath(__file__))
print(f"Base dir: {base_dir}")
local_db = os.path.join(base_dir, 'inventory.db')
print(f"Local DB: {local_db}")
print(f"Checking if Local DB exists...")
exists = os.path.exists(local_db)
print(f"Exists: {exists}")
print("Done.")
