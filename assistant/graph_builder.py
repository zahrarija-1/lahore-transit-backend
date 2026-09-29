from __future__ import annotations

import os
import sqlite3
from collections import defaultdict
from typing import Optional


DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "transit_ai.db",
)


def normalize(value: str) -> str:
    if value is None:
        return ""

    value = str(value).strip().lower()

    for char in [
        ",",
        ".",
        "-",
        "_",
        "/",
        "\\",
        "(",
        ")",
        "[",
        "]",
    ]:
        value = value.replace(char, " ")

    return " ".join(value.split())


class TransitGraph:
    def __init__(self):
        self.stop_name = {}
        self.stop_ids_by_norm = defaultdict(list)

        self.adjacency = defaultdict(list)

        self.routes_by_stop = defaultdict(set)

        self.route_info = {}

        self.stops_by_route = defaultdict(list)

        self.stop_coordinates = {}

    # =========================================================
    # BASIC STOP HELPERS
    # =========================================================

    def coordinates_of(
        self,
        stop_id: str,
    ) -> Optional[tuple[float, float]]:
        return self.stop_coordinates.get(stop_id)

    def get_stop_name(
        self,
        stop_id: str,
    ) -> Optional[str]:
        return self.stop_name.get(stop_id)

    def name_of(
        self,
        stop_id: str,
    ) -> str:
        """
        Return the display name of a stop.

        Used by routing_engine and handlers.
        If the stop ID is unknown, return the ID itself.
        """
        return self.stop_name.get(
            stop_id,
            stop_id,
        )

    # =========================================================
    # ROUTE HELPERS
    # =========================================================

    def get_route_info(
        self,
        route_id: str,
    ) -> Optional[dict]:
        return self.route_info.get(route_id)

    def get_routes_for_stop(
        self,
        stop_id: str,
    ):
        return self.routes_by_stop.get(
            stop_id,
            set(),
        )

    def get_stops_for_route(
        self,
        route_id: str,
    ):
        return self.stops_by_route.get(
            route_id,
            [],
        )

    # =========================================================
    # ROUTING HELPERS
    # =========================================================

    def neighbours(
        self,
        stop_id: str,
    ):
        """
        Return neighbouring stops.

        Each item is:
            (next_stop_id, route_id)
        """
        return self.adjacency.get(
            stop_id,
            [],
        )

    def transfer_stops(self):
        """
        Return stops served by more than one route.
        """
        return [
            stop_id
            for stop_id, routes
            in self.routes_by_stop.items()
            if len(routes) > 1
        ]

    # =========================================================
    # STOP SEARCH
    # =========================================================

    def find_stop_ids(
        self,
        stop_name: str,
    ):
        normalized = normalize(stop_name)

        if not normalized:
            return []

        return list(
            self.stop_ids_by_norm.get(
                normalized,
                [],
            )
        )

    def search_stops(
        self,
        query: str,
    ):
        normalized_query = normalize(query)

        if not normalized_query:
            return []

        results = []

        for stop_id, stop_name in self.stop_name.items():

            normalized_name = normalize(
                stop_name
            )

            if normalized_query in normalized_name:

                coordinates = self.coordinates_of(
                    stop_id
                )

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

    # =========================================================
    # DATABASE → GRAPH
    # =========================================================

    def build_graph(
        self,
        db_path: str = DB_PATH,
    ):

        if not os.path.exists(db_path):
            raise FileNotFoundError(
                f"Transit database not found: {db_path}"
            )

        # Clear old graph data
        self.stop_name.clear()
        self.stop_ids_by_norm.clear()
        self.adjacency.clear()
        self.routes_by_stop.clear()
        self.route_info.clear()
        self.stops_by_route.clear()
        self.stop_coordinates.clear()

        conn = sqlite3.connect(
            db_path
        )

        conn.row_factory = sqlite3.Row

        try:

            cursor = conn.cursor()

            # =================================================
            # LOAD STOPS
            # =================================================

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

                self.stop_name[
                    stop_id
                ] = stop_name

                normalized_name = normalize(
                    stop_name
                )

                if normalized_name:

                    self.stop_ids_by_norm[
                        normalized_name
                    ].append(
                        stop_id
                    )

                # Coordinates
                if (
                    row["latitude"] is not None
                    and
                    row["longitude"] is not None
                ):

                    try:

                        self.stop_coordinates[
                            stop_id
                        ] = (
                            float(
                                row["latitude"]
                            ),
                            float(
                                row["longitude"]
                            ),
                        )

                    except (
                        TypeError,
                        ValueError,
                    ):

                        pass

            # =================================================
            # LOAD ROUTES
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

                self.route_info[
                    row["route_id"]
                ] = dict(row)

            # =================================================
            # LOAD ROUTE STOPS
            # =================================================

            route_stop_rows = cursor.execute(
                """
                SELECT
                    route_id,
                    stop_sequence,
                    stop_id
                FROM route_stops
                ORDER BY
                    route_id,
                    stop_sequence
                """
            ).fetchall()

            for row in route_stop_rows:

                route_id = row["route_id"]

                stop_id = row["stop_id"]

                self.stops_by_route[
                    route_id
                ].append(
                    stop_id
                )

                self.routes_by_stop[
                    stop_id
                ].add(
                    route_id
                )

            # =================================================
            # BUILD ROUTING GRAPH
            # =================================================

            for (
                route_id,
                stop_ids
            ) in self.stops_by_route.items():

                for i in range(
                    len(stop_ids) - 1
                ):

                    current_stop = (
                        stop_ids[i]
                    )

                    next_stop = (
                        stop_ids[i + 1]
                    )

                    # Ignore invalid self-loop
                    if (
                        current_stop
                        ==
                        next_stop
                    ):
                        continue

                    # Forward direction
                    self.adjacency[
                        current_stop
                    ].append(
                        (
                            next_stop,
                            route_id,
                        )
                    )

                    # Reverse direction
                    self.adjacency[
                        next_stop
                    ].append(
                        (
                            current_stop,
                            route_id,
                        )
                    )

        finally:

            conn.close()

        return self


# =============================================================
# GLOBAL GRAPH INSTANCE
# =============================================================

_graph: Optional[
    TransitGraph
] = None


def get_graph(
    db_path: str = DB_PATH,
    force_reload: bool = False,
) -> TransitGraph:

    global _graph

    if (
        _graph is None
        or force_reload
    ):

        graph = TransitGraph()

        graph.build_graph(
            db_path
        )

        _graph = graph

    return _graph


# =============================================================
# DIRECT TEST
# =============================================================

if __name__ == "__main__":

    graph = get_graph(
        force_reload=True
    )

    print(
        "========================================"
    )

    print(
        "Transit Graph Built Successfully"
    )

    print(
        "========================================"
    )

    print(
        f"Stops: {len(graph.stop_name)}"
    )

    print(
        f"Routes: {len(graph.route_info)}"
    )

    print(
        f"Route-stop groups: "
        f"{len(graph.stops_by_route)}"
    )

    print(
        f"Stops with coordinates: "
        f"{len(graph.stop_coordinates)}"
    )

    if graph.stop_name:

        first_stop_id = next(
            iter(
                graph.stop_name
            )
        )

        print()

        print(
            "First stop:"
        )

        print(
            "ID:",
            first_stop_id,
        )

        print(
            "Name:",
            graph.name_of(
                first_stop_id
            ),
        )

        print(
            "Coordinates:",
            graph.coordinates_of(
                first_stop_id
            ),
        )