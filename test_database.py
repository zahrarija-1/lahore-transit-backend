import sqlite3

conn = sqlite3.connect("transit_ai.db")
cursor = conn.cursor()

# Show routes
cursor.execute("SELECT * FROM routes LIMIT 5")

routes = cursor.fetchall()

print("\n🚌 ROUTES:")
for route in routes:
    print(route)

# Show stops
cursor.execute("SELECT * FROM stops LIMIT 5")

stops = cursor.fetchall()

print("\n📍 STOPS:")
for stop in stops:
    print(stop)

conn.close()