"""
Transit AI - Tables for things the user creates.

The existing tables hold transport data, which comes from CSV files and is
rebuilt on every import. These hold user data, which must never be wiped by
a data reload, so they live in their own file and are created separately.

Run once:

    cd backend
    python migrations/app_tables.py

Safe to run again. CREATE TABLE IF NOT EXISTS does nothing when the table
is already there, and no DELETE runs anywhere in this file.
"""

import os
import sqlite3
import sys

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "transit_ai.db")


def create_app_tables(db_path=DB_PATH):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Foreign keys are off by default in SQLite and have to be asked for
    # on every connection. Without this, a delete leaves orphan rows.
    cursor.execute("PRAGMA foreign_keys = ON")

    # ==================================================================
    # SAVED PLACES
    # ==================================================================
    # Home, work and anywhere else the user travels often, so the trip
    # planner can offer them instead of asking them to type an address.
    #
    # The place may be one of our stops (stop_id set) or an arbitrary
    # point the user dropped on the map (stop_id null, coordinates set).
    # Both are stored the same way so the planner does not need two paths.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS saved_places (
            place_id    TEXT PRIMARY KEY,
            user_id     TEXT NOT NULL,
            label       TEXT NOT NULL,
            kind        TEXT NOT NULL DEFAULT 'other',
            stop_id     TEXT,
            latitude    REAL,
            longitude   REAL,
            address     TEXT,
            created_at  TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
            FOREIGN KEY (stop_id) REFERENCES stops(stop_id),
            CHECK (kind IN ('home', 'work', 'other')),
            CHECK (stop_id IS NOT NULL
                   OR (latitude IS NOT NULL AND longitude IS NOT NULL))
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_saved_places_user
        ON saved_places(user_id)
    """)

    # One home and one work per person. A second 'home' should replace the
    # first, not sit beside it, and the database is the right place to
    # enforce that rather than trusting every code path to remember.
    cursor.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_saved_places_unique_kind
        ON saved_places(user_id, kind)
        WHERE kind IN ('home', 'work')
    """)

    # ==================================================================
    # FAVOURITE ROUTES
    # ==================================================================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS favourite_routes (
            user_id     TEXT NOT NULL,
            route_id    TEXT NOT NULL,
            created_at  TEXT NOT NULL,
            PRIMARY KEY (user_id, route_id),
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
            FOREIGN KEY (route_id) REFERENCES routes(route_id)
        )
    """)

    # ==================================================================
    # TRIP HISTORY
    # ==================================================================
    # Every journey search. Three uses: showing recent trips so the user
    # can repeat one in a tap, clearing search history from Settings, and
    # -- the interesting one -- a record of which origin/destination pairs
    # people actually ask for, which is the only demand data this project
    # will ever have.
    #
    # Stop names rather than ids, because a user can search for a place
    # that is not in our data, and that search is still worth recording.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS trip_history (
            trip_id       TEXT PRIMARY KEY,
            user_id       TEXT NOT NULL,
            origin        TEXT NOT NULL,
            destination   TEXT NOT NULL,
            origin_id     TEXT,
            destination_id TEXT,
            route_found   INTEGER NOT NULL DEFAULT 0,
            route_id      TEXT,
            searched_at   TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_trip_history_user_time
        ON trip_history(user_id, searched_at DESC)
    """)

    # ==================================================================
    # CHAT MESSAGES
    # ==================================================================
    # assistant/session.py keeps the last few turns in memory, which is
    # enough for context but vanishes on restart. This is the durable
    # copy, so "Keep chat history" in Settings means something and the
    # Delete button has something to delete.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chat_messages (
            message_id  TEXT PRIMARY KEY,
            user_id     TEXT NOT NULL,
            session_id  TEXT NOT NULL,
            role        TEXT NOT NULL,
            content     TEXT NOT NULL,
            intent      TEXT,
            created_at  TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
            CHECK (role IN ('user', 'assistant'))
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_chat_user_session
        ON chat_messages(user_id, session_id, created_at)
    """)

    # ==================================================================
    # USER PREFERENCES
    # ==================================================================
    # The settings that change what the backend returns: which transport
    # types to include, how far the user will walk, whether to favour
    # fewer transfers. Appearance settings stay on the device -- the
    # server has no reason to know about a theme.
    #
    # One row per user, so the whole object is read in a single lookup.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_preferences (
            user_id                 TEXT PRIMARY KEY,
            modes                   TEXT NOT NULL DEFAULT 'Metrobus,Feeder',
            max_walk_m              INTEGER NOT NULL DEFAULT 800,
            prefer_fewest_transfers INTEGER NOT NULL DEFAULT 1,
            notifications_enabled   INTEGER NOT NULL DEFAULT 0,
            service_alerts          INTEGER NOT NULL DEFAULT 1,
            crowd_alerts            INTEGER NOT NULL DEFAULT 0,
            updated_at              TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
            CHECK (max_walk_m BETWEEN 100 AND 5000)
        )
    """)

    # ==================================================================
    # ISSUE REPORTS
    # ==================================================================
    # Corrections sent from the app: a stop in the wrong place, a route
    # that no longer runs. Nothing here edits transport data directly --
    # a report is a request for a human to look, which is why it carries
    # a status.
    #
    # user_id is nullable so a signed-out user can still report a problem.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS issue_reports (
            report_id     TEXT PRIMARY KEY,
            user_id       TEXT,
            kind          TEXT NOT NULL,
            subject       TEXT NOT NULL,
            details       TEXT NOT NULL,
            contact_email TEXT,
            status        TEXT NOT NULL DEFAULT 'open',
            created_at    TEXT NOT NULL,
            resolved_at   TEXT,
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE SET NULL,
            CHECK (status IN ('open', 'reviewing', 'accepted', 'rejected'))
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_reports_status
        ON issue_reports(status, created_at DESC)
    """)

    conn.commit()

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = sorted(row[0] for row in cursor.fetchall())

    conn.close()

    return tables


if __name__ == "__main__":
    print("Creating app tables...")
    tables = create_app_tables()

    app_tables = [
        "saved_places", "favourite_routes", "trip_history",
        "chat_messages", "user_preferences", "issue_reports",
    ]

    print()
    for name in app_tables:
        mark = "ok" if name in tables else "MISSING"
        print(f"  [{mark:>7}] {name}")

    print()
    print(f"{len(tables)} tables in the database:")
    print(f"  {', '.join(tables)}")
    print()
    print("Transport tables are rebuilt by database.py on every import.")
    print("These are not, so user data survives a data reload.")

    sys.exit(0)