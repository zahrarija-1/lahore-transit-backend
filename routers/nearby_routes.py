from __future__ import annotations

import math
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from supabase_client import supabase


router = APIRouter(
    prefix="/nearby",
    tags=["Nearby"],
)


# ============================================================
# Distance
# ============================================================

def haversine_km(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> float:
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
# Nearby
# ============================================================

@router.get("")
def nearby_stops(
    latitude: float = Query(..., ge=-90, le=90),
    longitude: float = Query(..., ge=-180, le=180),
    radius_km: float = Query(3.0, gt=0, le=50),
    limit: int = Query(10, ge=1, le=50),
):
    """
    Find real Lahore transit stops near the user's GPS location.

    Coordinates come directly from Supabase.
    Route information also comes from Supabase.
    """

    try:
        # ----------------------------------------------------
        # 1. Get real stops from Supabase
        # ----------------------------------------------------

        stop_response = (
            supabase
            .table("stops")
            .select(
                "stop_id,"
                "stop_name,"
                "city,"
                "latitude,"
                "longitude,"
                "source_url"
            )
            .execute()
        )

        stops = stop_response.data or []

        # ----------------------------------------------------
        # 2. Find nearby stops
        # ----------------------------------------------------

        nearby = []

        for stop in stops:

            if (
                stop.get("latitude") is None
                or stop.get("longitude") is None
            ):
                continue

            try:
                stop_lat = float(stop["latitude"])
                stop_lon = float(stop["longitude"])
            except (TypeError, ValueError):
                continue

            distance = haversine_km(
                latitude,
                longitude,
                stop_lat,
                stop_lon,
            )

            if distance <= radius_km:
                nearby.append(
                    {
                        "stop_id": stop["stop_id"],
                        "stop_name": stop["stop_name"],
                        "city": stop.get("city"),
                        "latitude": stop_lat,
                        "longitude": stop_lon,
                        "distance_km": round(
                            distance,
                            3,
                        ),
                        "source_url": stop.get(
                            "source_url"
                        ),
                    }
                )

        # ----------------------------------------------------
        # 3. Nearest first
        # ----------------------------------------------------

        nearby.sort(
            key=lambda item: item["distance_km"]
        )

        nearby = nearby[:limit]

        # ----------------------------------------------------
        # 4. No nearby stops
        # ----------------------------------------------------

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
                    "No transit stops found within "
                    f"{radius_km} km."
                ),
            }

        # ----------------------------------------------------
        # 5. Get route-stop relationships
        # ----------------------------------------------------

        stop_ids = [
            stop["stop_id"]
            for stop in nearby
        ]

        route_stop_response = (
            supabase
            .table("route_stops")
            .select(
                "route_id,"
                "stop_sequence,"
                "stop_id,"
                "stop_name,"
                "source_url"
            )
            .in_("stop_id", stop_ids)
            .execute()
        )

        route_stop_rows = (
            route_stop_response.data or []
        )

        # ----------------------------------------------------
        # 6. Collect route IDs
        # ----------------------------------------------------

        route_ids = sorted(
            {
                row["route_id"]
                for row in route_stop_rows
                if row.get("route_id")
            }
        )

        # ----------------------------------------------------
        # 7. Get route details
        # ----------------------------------------------------

        route_map: dict[str, dict[str, Any]] = {}

        if route_ids:

            route_response = (
                supabase
                .table("routes")
                .select(
                    "route_id,"
                    "route_type,"
                    "system,"
                    "origin,"
                    "destination,"
                    "stop_count,"
                    "fare_rs,"
                    "currency,"
                    "operating_hours,"
                    "headway_note,"
                    "source_url,"
                    "source_status"
                )
                .in_("route_id", route_ids)
                .execute()
            )

            for route in (
                route_response.data or []
            ):
                route_map[
                    route["route_id"]
                ] = route

        # ----------------------------------------------------
        # 8. Attach routes to each nearby stop
        # ----------------------------------------------------

        for stop in nearby:

            stop_id = stop["stop_id"]

            serving_route_ids = {
                row["route_id"]
                for row in route_stop_rows
                if row.get("stop_id") == stop_id
                and row.get("route_id")
            }

            routes = []

            for route_id in sorted(
                serving_route_ids
            ):

                route = route_map.get(route_id)

                if not route:
                    continue

                routes.append(
                    {
                        "route_id": route.get(
                            "route_id"
                        ),
                        "route_type": route.get(
                            "route_type"
                        ),
                        "system": route.get(
                            "system"
                        ),
                        "origin": route.get(
                            "origin"
                        ),
                        "destination": route.get(
                            "destination"
                        ),
                        "stop_count": route.get(
                            "stop_count"
                        ),
                        "fare_rs": route.get(
                            "fare_rs"
                        ),
                        "currency": route.get(
                            "currency"
                        ),
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

        # ----------------------------------------------------
        # 9. Final response
        # ----------------------------------------------------

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

    except Exception as exc:

        print(
            "Nearby endpoint error:",
            repr(exc),
        )

        raise HTTPException(
            status_code=500,
            detail=f"Nearby service error: {exc}",
        )