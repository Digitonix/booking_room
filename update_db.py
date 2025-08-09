import sqlite3

conn = sqlite3.connect('instance/booking.db')
conn.execute('ALTER TABLE room ADD COLUMN image TEXT;')
conn.commit()
conn.close()
