"""
Builds the transit graph from the SQLite database.

Nodes  = stops (stop_id)
Edges  = "these two stops are consecutive on route X"

The graph is built once at startup and kept in memory. With 316 stops and
363 route_stop rows this takes a few milliseconds, so there is no need to
pickle it to disk.

ASSUMPTION (state this in your FYP report): routes are treated as
bidirectional, because route_stops.csv lists one direction only. Real
feeder routes may differ slightly in the return direction.
"""

import os
import re
import sqlite3
from collections import defaultdict

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "transit_ai.db")


def normalize(text):
    """Lowercase, strip punctuation, collapse spaces. Used for name matching."""
    if not text:
        return ""
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


class TransitGraph:
    def __init__(self):
        self.stop_name = {}                     # stop_id -> display name
        self.stop_ids_by_norm = defaultdict(list)  # normalized name -> [stop_id]
        self.adjacency = defaultdict(list)      # stop_id -> [(neighbour_id, route_id)]
        self.routes_by_stop = defaultdict(set)  # stop_id -> {route_id}
        self.route_info = {}                    # route_id -> dict from routes table
        self.stops_by_route = defaultdict(list)  # route_id -> [stop_id] in sequence

    # -- lookups -----------------------------------------------------------

    def neighbours(self, stop_id):
        return self.adjacency.get(stop_id, [])

    def name_of(self, stop_id):
        return self.stop_name.get(stop_id, stop_id)

    def transfer_stops(self):
        """Stops served by more than one route."""
        return [s for s, r in self.routes_by_stop.items() if len(r) > 1]


def build_graph(db_path=DB_PATH):
    """Read the database and return a ready-to-use TransitGraph."""
    if not os.path.exists(db_path):
        raise FileNotFoundError(
            f"Database not found at {db_path}. Run: python database.py"
        )

    graph = TransitGraph()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 1. Stops
    for row in cursor.execute("SELECT stop_id, stop_name FROM stops"):
        graph.stop_name[row["stop_id"]] = row["stop_name"]
        graph.stop_ids_by_norm[normalize(row["stop_name"])].append(row["stop_id"])

    # 2. Routes (used for fares and system names)
    for row in cursor.execute(
        "SELECT route_id, route_type, system, origin, destination, "
        "fare_rs, operating_hours FROM routes"
    ):
        graph.route_info[row["route_id"]] = dict(row)

    # 3. Route stops, in sequence -> edges
    cursor.execute(
        "SELECT route_id, stop_sequence, stop_id FROM route_stops "
        "ORDER BY route_id, stop_sequence"
    )
    sequences = defaultdict(list)
    for row in cursor.fetchall():
        sequences[row["route_id"]].append(row["stop_id"])

    for route_id, stop_ids in sequences.items():
        graph.stops_by_route[route_id] = stop_ids
        for stop_id in stop_ids:
            graph.routes_by_stop[stop_id].add(route_id)
        for a, b in zip(stop_ids, stop_ids[1:]):
            if a == b:
                continue
            graph.adjacency[a].append((b, route_id))
            graph.adjacency[b].append((a, route_id))  # bidirectional assumption

    conn.close()
    return graph


# Built once, imported by the rest of the assistant.
_graph = None


def get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph


if __name__ == "__main__":
    g = build_graph()
    print(f"Stops loaded      : {len(g.stop_name)}")
    print(f"Routes with stops : {len(g.stops_by_route)}")
    print(f"Transfer stops    : {len(g.transfer_stops())}")
    sample = g.transfer_stops()[0]
    print(f"\nNeighbours of {g.name_of(sample)} ({sample}):")
    for neighbour, route_id in g.neighbours(sample):
        print(f"   -> {g.name_of(neighbour):<30} via {route_id}")