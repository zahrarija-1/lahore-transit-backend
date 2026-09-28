import sqlite3
import csv
import os

# Database location
DB_PATH = "transit_ai.db"

# CSV folder
DATA_DIR = "data"


def create_database():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # =========================
    # AGENCY
    # =========================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS agency (
            agency_id TEXT PRIMARY KEY,
            agency_name TEXT,
            city TEXT,
            country TEXT,
            website TEXT,
            source_status TEXT
        )
    """)

    # =========================
    # ROUTES
    # =========================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS routes (
            route_id TEXT PRIMARY KEY,
            route_type TEXT,
            system TEXT,
            origin TEXT,
            destination TEXT,
            stop_count INTEGER,
            fare_rs REAL,
            currency TEXT,
            operating_hours TEXT,
            headway_note TEXT,
            source_url TEXT,
            source_status TEXT
        )
    """)

    # =========================
    # STOPS
    # =========================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS stops (
            stop_id TEXT PRIMARY KEY,
            stop_name TEXT,
            city TEXT,
            latitude REAL,
            longitude REAL,
            source_url TEXT
        )
    """)

    # =========================
    # ROUTE STOPS
    # =========================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS route_stops (
            route_id TEXT,
            stop_sequence INTEGER,
            stop_id TEXT,
            stop_name TEXT,
            source_url TEXT,
            FOREIGN KEY (route_id) REFERENCES routes(route_id),
            FOREIGN KEY (stop_id) REFERENCES stops(stop_id)
        )
    """)

    # =========================
    # FARES
    # =========================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS fares (
            service_type TEXT,
            fare_rule TEXT,
            fare_rs REAL,
            currency TEXT,
            source_url TEXT,
            source_status TEXT
        )
    """)

    # =========================
    # SERVICES
    # =========================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS services (
            service_id TEXT PRIMARY KEY,
            service TEXT,
            origin TEXT,
            destination TEXT,
            operating_hours TEXT,
            headway TEXT,
            source_url TEXT
        )
    """)

    # =========================
    # FAQ
    # =========================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transit_faq (
            question TEXT,
            answer TEXT,
            source_url TEXT
        )
    """)

    # =========================
    # METROBUS
    # =========================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS metrobus_system (
            route_id TEXT PRIMARY KEY,
            line TEXT,
            origin TEXT,
            destination TEXT,
            corridor_length_km REAL,
            stations INTEGER,
            buses INTEGER,
            operating_hours TEXT,
            headway TEXT,
            source_url TEXT
        )
    """)

    # =========================
    # DISRUPTIONS
    # =========================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS disruptions (
            timestamp TEXT,
            route_id TEXT,
            status TEXT,
            reason TEXT,
            start_time TEXT,
            end_time TEXT,
            source_url TEXT
        )
    """)

    # =========================
    # USERS
    # =========================
    # COLLATE NOCASE means Ali@Test.com and ali@test.com are treated
    # as the same address, so one person cannot create two accounts
    # by changing the capitalisation.
    #
    # SQLite has no BOOLEAN type, so is_active is an INTEGER: 1 or 0.
    # It has no DATETIME type either, so timestamps are ISO strings.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            email TEXT UNIQUE NOT NULL COLLATE NOCASE,
            password_hash TEXT NOT NULL,
            full_name TEXT,
            role TEXT NOT NULL DEFAULT 'user',
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_users_email
        ON users(email)
    """)

    conn.commit()

    # Import CSV files
    import_csv(cursor, "agency", "agency.csv")
    import_csv(cursor, "routes", "routes.csv")
    import_csv(cursor, "stops", "stops.csv")
    import_csv(cursor, "route_stops", "route_stops.csv")
    import_csv(cursor, "fares", "fares.csv")
    import_csv(cursor, "services", "services.csv")
    import_csv(cursor, "transit_faq", "transit_faq.csv")
    import_csv(cursor, "metrobus_system", "metrobus_system.csv")
    import_csv(cursor, "disruptions", "disruptions.csv")

    conn.commit()
    conn.close()

    print("✅ Transit AI database created successfully!")
    print(f"📁 Database: {DB_PATH}")


def import_csv(cursor, table_name, filename):
    """
    Load a CSV file into a table.

    The table is emptied first, so the CSV file is always the single
    source of truth and running this script twice cannot create
    duplicate rows. Tables without a PRIMARY KEY (route_stops, fares,
    transit_faq, disruptions) would otherwise be duplicated on every
    run, because INSERT OR IGNORE has no key to detect a repeat with.

    The users table is never imported here, so account data is safe.
    """

    filepath = os.path.join(DATA_DIR, filename)

    if not os.path.exists(filepath):
        print(f"⚠️ File not found: {filename} — {table_name} left unchanged")
        return

    with open(filepath, "r", encoding="utf-8-sig") as file:

        reader = csv.reader(file)
        headers = next(reader)

        rows = list(reader)

        if not rows:
            print(f"⚠️ {filename} has no data rows — {table_name} left unchanged")
            return

        # Reject rows whose column count does not match the header,
        # so one broken line cannot shift every value into the wrong
        # column.
        expected = len(headers)
        valid_rows = []
        bad_rows = 0

        for row in rows:
            if len(row) == expected:
                valid_rows.append(row)
            else:
                bad_rows += 1

        if bad_rows:
            print(f"⚠️ {filename}: skipped {bad_rows} malformed row(s)")

        if not valid_rows:
            print(f"⚠️ {filename}: no valid rows — {table_name} left unchanged")
            return

        cursor.execute(f"DELETE FROM {table_name}")

        placeholders = ",".join(["?"] * expected)

        cursor.executemany(
            f"INSERT INTO {table_name} VALUES ({placeholders})",
            valid_rows
        )

        print(f"✅ Imported {len(valid_rows)} rows → {table_name}")


if __name__ == "__main__":
    create_database()