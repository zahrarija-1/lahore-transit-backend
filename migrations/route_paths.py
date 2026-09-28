"""
Transit AI - Route geometry.

lahore_route_paths.csv holds the shape of each route: thousands of points
tracing the roads the bus actually uses. Drawing a line between stops
instead would cut across buildings and the river.

Stored in its own table rather than a CSV import in database.py, because
it is large (7,667 rows) and changes far less often than the stop data.

    cd backend
    python migrations/route_paths.py path/to/lahore_route_paths.csv

Safe to run again: the table is rebuilt from the file each time, and it
holds nothing a user created.
"""

import csv
import os
import sqlite3
import sys
from collections import defaultdict

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "transit_ai.db")

LAT_MIN, LAT_MAX = 31.20, 31.80
LON_MIN, LON_MAX = 74.00, 74.70


def create_table(cursor):
    # One row per point. Reading a route means selecting its points and
    # ordering by point_sequence, which the index below makes cheap.
    #
    # direction: a route out is not the same as the route back. One-way
    # streets and central reservations mean the two lines differ, so both
    # are stored and the app asks for the one it needs.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS route_paths (
            route_id       TEXT NOT NULL,
            direction      TEXT NOT NULL,
            point_sequence INTEGER NOT NULL,
            latitude       REAL NOT NULL,
            longitude      REAL NOT NULL,
            PRIMARY KEY (route_id, direction, point_sequence),
            FOREIGN KEY (route_id) REFERENCES routes(route_id),
            CHECK (latitude BETWEEN 31.20 AND 31.80),
            CHECK (longitude BETWEEN 74.00 AND 74.70)
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_route_paths_lookup
        ON route_paths(route_id, direction, point_sequence)
    """)


def main():
    if len(sys.argv) < 2:
        print("Usage: python migrations/route_paths.py "
              "<lahore_route_paths.csv>")
        return 1

    source_path = sys.argv[1]
    if not os.path.exists(source_path):
        print(f"Not found: {source_path}")
        return 1

    with open(source_path, "r", encoding="utf-8-sig", newline="") as handle:
        source = list(csv.DictReader(handle))

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    create_table(cursor)

    known_routes = {
        row[0] for row in cursor.execute("SELECT route_id FROM routes")
    }

    rows = []
    skipped_bad = 0
    skipped_unknown = defaultdict(int)
    seen = set()
    duplicates = 0

    for row in source:
        route_id = row.get("route_id", "").strip()
        direction = row.get("direction", "").strip() or "FW"

        if route_id not in known_routes:
            skipped_unknown[route_id] += 1
            continue

        try:
            sequence = int(row["point_sequence"])
            lat = float(row["latitude"])
            lon = float(row["longitude"])
        except (KeyError, TypeError, ValueError):
            skipped_bad += 1
            continue

        if not (LAT_MIN <= lat <= LAT_MAX and LON_MIN <= lon <= LON_MAX):
            skipped_bad += 1
            continue

        key = (route_id, direction, sequence)
        if key in seen:
            duplicates += 1
            continue
        seen.add(key)

        rows.append((route_id, direction, sequence, lat, lon))

    # Rebuilt wholesale, so a re-run cannot leave stale points behind.
    cursor.execute("DELETE FROM route_paths")
    cursor.executemany(
        "INSERT INTO route_paths VALUES (?, ?, ?, ?, ?)",
        rows
    )
    conn.commit()

    print(f"{len(source)} rows read")
    print(f"  imported            : {len(rows)}")
    if duplicates:
        print(f"  duplicate sequences : {duplicates} (ignored)")
    if skipped_bad:
        print(f"  unusable coordinates: {skipped_bad} (ignored)")
    if skipped_unknown:
        total = sum(skipped_unknown.values())
        print(f"  unknown route_id    : {total} rows across "
              f"{len(skipped_unknown)} route(s): "
              f"{', '.join(sorted(skipped_unknown))}")

    print()
    print("Coverage:")

    query = """
        SELECT r.route_id, r.route_type,
               (SELECT COUNT(*) FROM route_paths p
                WHERE p.route_id = r.route_id) AS points
        FROM routes r
        ORDER BY points ASC, r.route_id
    """
    missing = []
    for route_id, route_type, points in cursor.execute(query):
        if points == 0:
            missing.append(route_id)
            print(f"  {route_id:<8} {route_type:<10} no geometry")
        else:
            print(f"  {route_id:<8} {route_type:<10} {points:>5} points")

    conn.close()

    if missing:
        print()
        print(f"{len(missing)} route(s) cannot be drawn on the map: "
              f"{', '.join(missing)}")
        print("The app should fall back to a straight line between stops")
        print("for these, and say so, rather than drawing nothing.")

    return 0


if __name__ == "__main__":
    sys.exit(main())