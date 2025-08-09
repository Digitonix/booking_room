import sqlite3
conn = sqlite3.connect('instance/booking.db')
cursor = conn.execute('PRAGMA table_info(room);')
for row in cursor:
    print(row)
conn.close()
