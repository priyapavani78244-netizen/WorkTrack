import sqlite3

conn = sqlite3.connect("employee.db")
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS leave_request (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id TEXT NOT NULL,
    leave_date TEXT NOT NULL,
    reason TEXT NOT NULL,
    status TEXT DEFAULT 'Pending'
)
""")

conn.commit()
conn.close()

print("Leave Request Table Created Successfully")