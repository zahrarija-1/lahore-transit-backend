"""
Transit AI - Transport data endpoints.

These give the Flutter app direct access to routes, stops, fares and
journey search, without going through the AI assistant. A list screen
or a map screen needs plain data, not a chat reply.

Every function here calls a tool in db_tools.py, which is the same
code the AI agent uses. One source of truth, two ways in.
"""

from fastapi import APIRouter, HTTPException, Query, status

from db_tools import (
    fare_calculator,
    get_route_stops,
    get_stop_routes,
    list_routes,
    list_services,
    list_stops,
    route_information,
    route_search,
)

router = APIRouter(
    prefix="/transport",
    tags=["Transport"]
)


# ============================================================
# ROUTES
# ============================================================

@router.get("/routes")
def all_routes(
    route_type: str | None = Query(
        default=None,
        description="Filter by type, for example 'Feeder' or 'Metrobus'."
    )
):
    """List every route in the database."""

    return list_routes(route_type=route_type)


@router.get("/routes/{route_id}")
def one_route(route_id: str):
    """Full details of a single route."""

    result = route_information(route_id)

    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=result["message"]
        )

    return result


@router.get("/routes/{route_id}/stops")
def route_stops(route_id: str):
    """All stops of a route, in travel order."""

    result = get_route_stops(route_id)

    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=result["message"]
        )

    return result


# ============================================================
# STOPS
# ============================================================

@router.get("/stops")
def all_stops(
    search: str | None = Query(
        default=None,
        description="Filter stops by name."
    ),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0)
):
    """
    List stops, with optional name search.

    Paged, because returning all 316 stops on a mobile screen at once
    is wasteful. Flutter can request the next page as the user scrolls.
    """

    return list_stops(
        search=search,
        limit=limit,
        offset=offset
    )


@router.get("/stops/{stop_name}/routes")
def routes_at_stop(stop_name: str):
    """Which routes serve a given stop."""

    result = get_stop_routes(stop_name)

    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=result["message"]
        )

    return result


# ============================================================
# JOURNEY SEARCH
# ============================================================

@router.get("/search")
def search_journey(
    origin: str = Query(min_length=2, description="Starting stop name."),
    destination: str = Query(min_length=2, description="Destination stop name.")
):
    """
    Find direct routes between two stops.

    Only direct routes are returned. Transfers between routes are not
    calculated, so an empty result means no single route covers the
    journey, not that the journey is impossible.
    """

    result = route_search(origin, destination)

    if not result["success"]:

        # A stop the user typed does not exist in our data.
        if result.get("error") in ("origin_not_found", "destination_not_found"):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=result["message"]
            )

        # Both stops exist, but no single route connects them. This is
        # a valid answer, not an error, so it returns 200.
        return result

    return result


# ============================================================
# FARES AND SERVICES
# ============================================================

@router.get("/fares")
def fares(
    service_type: str | None = Query(
        default=None,
        description="For example 'Metrobus' or 'Feeder'."
    )
):
    """Fare information."""

    result = fare_calculator(service_type=service_type)

    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=result["message"]
        )

    return result


@router.get("/services")
def services():
    """Operating hours and headway for each transport service."""

    return list_services()