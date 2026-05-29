import sqlite3
conn = sqlite3.connect('outreach.db')
c = conn.cursor()
c.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = c.fetchall()
print("Tables:", tables)

for t in tables:
    name = t[0]
    c.execute(f"PRAGMA table_info({name})")
    cols = c.fetchall()
    print(f"\n{name}: {[col[1] for col in cols]}")

conn.close()
