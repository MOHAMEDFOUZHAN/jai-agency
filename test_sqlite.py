import sqlite3
import os

db_name = 'test_db.db'
if os.path.exists(db_name):
    os.remove(db_name)

conn = sqlite3.connect(db_name)
c = conn.cursor()
c.execute('CREATE TABLE test (id INTEGER PRIMARY KEY, name TEXT)')
c.execute('INSERT INTO test (name) VALUES ("hello")')
conn.commit()
c.execute('SELECT * FROM test')
print(f"Result: {c.fetchone()}")
conn.close()
print("Test complete.")
