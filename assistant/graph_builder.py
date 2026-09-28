from __future__ import annotations

import os
import sqlite3
from collections import defaultdict
from typing import Optional


# ============================================================
# Database
# ============================================================

DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "transit_ai.db",
)


# ============================================================
# Text normalization
# ============================================================

def normalize(value: str) -> str:
    """
    Normalize stop names for searching/matching.
    """
    if value is None:
        return ""

    value = str(value).strip().lower()

    # Normalize common punctuation/spaces
    for char in [",", ".", "-", "_", "/", "\\", "(", ")", "[", "]"]:
        value = value.replace(char, " ")

    return " ".join(value.split())


# ============================================================
# Transit Graph
# ============================================================

class TransitGraph:
    def __init__(self):
        # stop_id -> stop_name
        self.stop_name = {}

        # normalized stop name -> list of stop_ids
        self.stop_ids_by_norm = defaultdict(list)

        # stop_id -> [(next_stop_id, route_id), ...]
        self.adjacency = defaultdict(list)

        # stop_id -> set(route_id)
        self.routes_by_stop = defaultdict(set)

        # route_id -> route information
        self.route_info = {}

        # route_id -> ordered list of stop_ids
        self.stops_by_route = defaultdict(list)

        # stop_id -> (latitude, longitude)
        self.stop_coordinates = {}

    # --------------------------------------------------------
    # Coordinates
    # --------------------------------------------------------

    def coordinates_of(self, stop_id: str) -> Optional[tuple[float, float]]:
        """
        Return (latitude, longitude) for a stop.
        Returns None if coordinates are unavailable.
        """
        return self.stop_coordinates.get(stop_id)

    # --------------------------------------------------------
    # Build graph
    # --------------------------------------------------------

    def build_graph(self, db_path: str = DB_PATH):
        """
        Build the complete transit graph from SQLite database.
        """

        if not os.path.exists(db_path):
            raise FileNotFoundError(
                f"Transit database not found: {db_path}"
            )

        # Reset graph in case build_graph() is called again
        self.stop_name.clear()
        self.stop_ids_by_norm.clear()
        self.adjacency.clear()
        self.routes_by_stop.clear()
        self.route_info.clear()
        self.stops_by_route.clear()
        self.stop_coordinates.clear()

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row

        try:
            cursor = conn.cursor()

            # =================================================
            # 1. Stops
            # =================================================
            #
            # IMPORTANT:
            # Coordinates are now loaded from SQLite.
            #

            stop_rows = cursor.execute(
                """
                SELECT
                    stop_id,
                    stop_name,
                    latitude,
                    longitude
                FROM stops
                """
            ).fetchall()

            for row in stop_rows:
                stop_id = row["stop_id"]
                stop_name = row["stop_name"]

                self.stop_name[stop_id] = stop_name

                normalized_name = normalize(stop_name)

                if normalized_name:
                    self.stop_ids_by_norm[normalized_name].append(
                        stop_id
                    )

                # Store coordinates only when both values exist
                if (
                    row["latitude"] is not None
                    and row["longitude"] is not None
                ):
                    try:
                        self.stop_coordinates[stop_id] = (
                            float(row["latitude"]),
                            float(row["longitude"]),
                        )
                    except (TypeError, ValueError):
                        pass

            # =================================================
            # 2. Routes
            # =================================================

            route_rows = cursor.execute(
                """
                SELECT
                    route_id,
                    route_type,
                    system,
                    origin,
                    destination,
                    fare_rs,
                    operating_hours
                FROM routes
                """
            ).fetchall()

            for row in route_rows:
                self.route_info[row["route_id"]] = dict(row)

            # =================================================
            # 3. Route Stops
            # =================================================

            route_stop_rows = cursor.execute(
                """
                SELECT
                    route_id,
                    stop_sequence,
                    stop_id
                FROM route_stops
                ORDER BY route_id, stop_sequence
                """
            ).fetchall()

            # Group stops by route
            for row in route_stop_rows:
                route_id = row["route_id"]
                stop_id = row["stop_id"]

                self.stops_by_route[route_id].append(stop_id)

                # Route serving this stop
                self.routes_by_stop[stop_id].add(route_id)

            # =================================================
            # 4. Build directed edges
            # =================================================

            for route_id, stop_ids in self.stops_by_route.items():

                # Connect each stop to the next stop
                for i in range(len(stop_ids) - 1):
                    current_stop = stop_ids[i]
                    next_stop = stop_ids[i + 1]

                    self.adjacency[current_stop].append(
                        (
                            next_stop,
                            route_id,
                        )
                    )

        finally:
            conn.close()

        return self

    # --------------------------------------------------------
    # Basic helpers
    # --------------------------------------------------------

    def get_stop_name(self, stop_id: str) -> Optional[str]:
        return self.stop_name.get(stop_id)

    def get_route_info(self, route_id: str) -> Optional[dict]:
        return self.route_info.get(route_id)

    def get_routes_for_stop(self, stop_id: str):
        return self.routes_by_stop.get(stop_id, set())

    def get_stops_for_route(self, route_id: str):
        return self.stops_by_route.get(route_id, [])

    # --------------------------------------------------------
    # Find stop IDs by name
    # --------------------------------------------------------

    def find_stop_ids(self, stop_name: str):
        """
        Return stop IDs matching a normalized stop name.
        """
        normalized = normalize(stop_name)

        if not normalized:
            return []

        return list(
            self.stop_ids_by_norm.get(normalized, [])
        )

    # --------------------------------------------------------
    # Find stops containing search text
    # --------------------------------------------------------

    def search_stops(self, query: str):
        """
        Search stops using partial name matching.
        Returns:
            [
                {
                    "stop_id": ...,
                    "stop_name": ...,
                    "latitude": ...,
                    "longitude": ...
                }
            ]
        """

        normalized_query = normalize(query)

        if not normalized_query:
            return []

        results = []

        for stop_id, stop_name in self.stop_name.items():

            normalized_name = normalize(stop_name)

            if normalized_query in normalized_name:

                coordinates = self.coordinates_of(stop_id)

                latitude = None
                longitude = None

                if coordinates:
                    latitude, longitude = coordinates

                results.append(
                    {
                        "stop_id": stop_id,
                        "stop_name": stop_name,
                        "latitude": latitude,
                        "longitude": longitude,
                    }
                )

        return results


# ============================================================
# Global graph
# ============================================================

_graph: Optional[TransitGraph] = None


# ============================================================
# Get graph
# ============================================================

def get_graph(
    db_path: str = DB_PATH,
    force_reload: bool = False,
) -> TransitGraph:
    """
    Return the global transit graph.

    The graph is built once and reused.
    """

    global _graph

    if _graph is None or force_reload:
        graph = TransitGraph()
        graph.build_graph(db_path)
        _graph = graph

    return _graph


# ============================================================
# Build graph immediately when requested directly
# ============================================================

if __name__ == "__main__":

    graph = get_graph(force_reload=True)

    print("========================================")
    print("Transit Graph Built Successfully")
    print("========================================")

    print(f"Stops: {len(graph.stop_name)}")
    print(f"Routes: {len(graph.route_info)}")
    print(f"Route-stop groups: {len(graph.stops_by_route)}")
    print(f"Stops with coordinates: {len(graph.stop_coordinates)}")

    # Test first stop
    if graph.stop_name:
        first_stop_id = next(iter(graph.stop_name))

        print()
        print("First stop:")
        print("ID:", first_stop_id)
        print("Name:", graph.stop_name[first_stop_id])
        print(
            "Coordinates:",
            graph.coordinates_of(first_stop_id),
        )