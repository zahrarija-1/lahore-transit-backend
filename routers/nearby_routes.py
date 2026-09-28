from __future__ import annotations

import math
import os
import sqlite3
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from assistant.graph_builder import get_graph


router = APIRouter(
    prefix="/nearby",
    tags=["Nearby"],
)


# ============================================================
# Database path
# ============================================================

DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "transit_ai.db",
)


# ============================================================
# Haversine distance
# ============================================================

def haversine_km(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> float:
    """
    Calculate straight-line distance between two GPS coordinates.
    Result is in kilometers.
    """

    earth_radius_km = 6371.0

    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)

    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1_rad)
        * math.cos(lat2_rad)
        * math.sin(delta_lon / 2) ** 2
    )

    c = 2 * math.atan2(
        math.sqrt(a),
        math.sqrt(1 - a),
    )

    return earth_radius_km * c


# ============================================================
# Route details from SQLite
# ============================================================

def get_route_details(route_ids: list[str]) -> dict[str, dict[str, Any]]:
    """
    Get complete route information from SQLite.
    """

    if not route_ids:
        return {}

    if not os.path.exists(DB_PATH):
        raise HTTPException(
            status_code=500,
            detail="Transit database not found.",
        )

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    try:
        placeholders = ",".join("?" for _ in route_ids)

        query = f"""
            SELECT
                route_id,
                route_type,
                system,
                origin,
                destination,
                fare_rs,
                currency,
                operating_hours,
                headway_note,
                source_url,
                source_status
            FROM routes
            WHERE route_id IN ({placeholders})
        """

        rows = conn.execute(
            query,
            route_ids,
        ).fetchall()

        return {
            row["route_id"]: dict(row)
            for row in rows
        }

    finally:
        conn.close()


# ============================================================
# Nearby endpoint
# ============================================================

@router.get("")
def nearby_stops(
    latitude: float = Query(
        ...,
        ge=-90,
        le=90,
        description="Current GPS latitude",
    ),
    longitude: float = Query(
        ...,
        ge=-180,
        le=180,
        description="Current GPS longitude",
    ),
    radius_km: float = Query(
        3.0,
        gt=0,
        le=50,
        description="Search radius in kilometers",
    ),
    limit: int = Query(
        10,
        ge=1,
        le=50,
        description="Maximum number of nearby stops",
    ),
):
    """
    Find real transit stops near the user's GPS location.

    Uses:
    - Real stop coordinates
    - Real route-stop relationships
    - Real route information
    - Real fares
    - Real operating hours
    - Real headway information
    """

    try:
        graph = get_graph()

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Unable to load transit graph: {exc}",
        )

    nearby = []

    # --------------------------------------------------------
    # Find nearby stops
    # --------------------------------------------------------

    for stop_id, coordinates in graph.stop_coordinates.items():

        stop_lat, stop_lon = coordinates

        distance = haversine_km(
            latitude,
            longitude,
            stop_lat,
            stop_lon,
        )

        if distance <= radius_km:

            nearby.append(
                {
                    "stop_id": stop_id,
                    "stop_name": graph.stop_name.get(
                        stop_id,
                        stop_id,
                    ),
                    "latitude": stop_lat,
                    "longitude": stop_lon,
                    "distance_km": round(distance, 3),
                }
            )

    # --------------------------------------------------------
    # Sort nearest first
    # --------------------------------------------------------

    nearby.sort(
        key=lambda item: item["distance_km"]
    )

    nearby = nearby[:limit]

    # --------------------------------------------------------
    # No stops found
    # --------------------------------------------------------

    if not nearby:
        return {
            "success": True,
            "user_location": {
                "latitude": latitude,
                "longitude": longitude,
            },
            "radius_km": radius_km,
            "count": 0,
            "stops": [],
            "message": (
                "No transit stops were found within "
                f"{radius_km} km."
            ),
        }

    # --------------------------------------------------------
    # Collect all routes serving these stops
    # --------------------------------------------------------

    route_ids = set()

    for stop in nearby:
        stop_routes = graph.get_routes_for_stop(
            stop["stop_id"]
        )

        route_ids.update(stop_routes)

    route_details = get_route_details(
        list(route_ids)
    )

    # --------------------------------------------------------
    # Attach route information
    # --------------------------------------------------------

    for stop in nearby:

        routes = []

        stop_routes = graph.get_routes_for_stop(
            stop["stop_id"]
        )

        for route_id in sorted(stop_routes):

            route = route_details.get(route_id)

            if not route:
                continue

            routes.append(
                {
                    "route_id": route.get("route_id"),
                    "route_type": route.get("route_type"),
                    "system": route.get("system"),
                    "origin": route.get("origin"),
                    "destination": route.get("destination"),
                    "fare_rs": route.get("fare_rs"),
                    "currency": route.get("currency"),
                    "operating_hours": route.get(
                        "operating_hours"
                    ),
                    "headway_note": route.get(
                        "headway_note"
                    ),
                    "source_url": route.get(
                        "source_url"
                    ),
                    "source_status": route.get(
                        "source_status"
                    ),
                }
            )

        stop["routes"] = routes
        stop["route_count"] = len(routes)

    # --------------------------------------------------------
    # Final response
    # --------------------------------------------------------

    return {
        "success": True,
        "user_location": {
            "latitude": latitude,
            "longitude": longitude,
        },
        "radius_km": radius_km,
        "count": len(nearby),
        "stops": nearby,
    }