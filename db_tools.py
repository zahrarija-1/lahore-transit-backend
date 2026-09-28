from typing import Any, Dict, List, Optional

from supabase_client import get_supabase


# ============================================================
# SUPABASE
# ============================================================

supabase = get_supabase()


# ============================================================
# ROUTES
# ============================================================

def get_all_routes() -> List[Dict[str, Any]]:
    response = (
        supabase
        .table("routes")
        .select("*")
        .execute()
    )

    return response.data or []


def list_routes() -> List[Dict[str, Any]]:
    return get_all_routes()


def get_route_by_id(
    route_id: str
) -> Optional[Dict[str, Any]]:

    response = (
        supabase
        .table("routes")
        .select("*")
        .eq("route_id", route_id)
        .limit(1)
        .execute()
    )

    if response.data:
        return response.data[0]

    return None


# ============================================================
# ROUTE STOPS
# ============================================================

def get_route_stops(
    route_id: str
) -> List[Dict[str, Any]]:

    response = (
        supabase
        .table("route_stops")
        .select("*")
        .eq("route_id", route_id)
        .order("stop_sequence")
        .execute()
    )

    return response.data or []


def get_stop_routes(
    stop_id: str
) -> List[Dict[str, Any]]:

    response = (
        supabase
        .table("route_stops")
        .select("*")
        .eq("stop_id", stop_id)
        .execute()
    )

    return response.data or []


# ============================================================
# STOPS
# ============================================================

def list_stops() -> List[Dict[str, Any]]:

    response = (
        supabase
        .table("stops")
        .select("*")
        .execute()
    )

    return response.data or []


def get_all_stops() -> List[Dict[str, Any]]:
    return list_stops()


def get_stop_by_id(
    stop_id: str
) -> Optional[Dict[str, Any]]:

    response = (
        supabase
        .table("stops")
        .select("*")
        .eq("stop_id", stop_id)
        .limit(1)
        .execute()
    )

    if response.data:
        return response.data[0]

    return None


def search_stops(
    stop_name: str
) -> List[Dict[str, Any]]:

    response = (
        supabase
        .table("stops")
        .select("*")
        .ilike(
            "stop_name",
            f"%{stop_name}%"
        )
        .limit(20)
        .execute()
    )

    return response.data or []


# ============================================================
# FARES
# ============================================================

def get_fares(
    service_type: Optional[str] = None
) -> List[Dict[str, Any]]:

    query = (
        supabase
        .table("fares")
        .select("*")
    )

    if service_type:
        query = query.ilike(
            "service_type",
            f"%{service_type}%"
        )

    response = query.execute()

    return response.data or []


def fare_calculator(
    service_type: str,
    default_fare: Optional[float] = None
) -> Dict[str, Any]:

    fares = get_fares(service_type)

    if fares:

        fare = fares[0]

        return {
            "service_type": fare.get("service_type"),
            "fare_rs": fare.get("fare_rs"),
            "currency": fare.get(
                "currency",
                "PKR"
            ),
            "fare_rule": fare.get(
                "fare_rule"
            ),
            "source_url": fare.get(
                "source_url"
            ),
        }

    if default_fare is not None:

        return {
            "service_type": service_type,
            "fare_rs": default_fare,
            "currency": "PKR",
            "fare_rule": "Default fare",
            "source_url": None,
        }

    return {
        "service_type": service_type,
        "fare_rs": None,
        "currency": "PKR",
        "fare_rule": "Fare not found",
        "source_url": None,
    }


# ============================================================
# SERVICES
# ============================================================

def get_services() -> List[Dict[str, Any]]:

    response = (
        supabase
        .table("services")
        .select("*")
        .execute()
    )

    return response.data or []


def list_services() -> List[Dict[str, Any]]:
    return get_services()


def get_service_by_id(
    service_id: str
) -> Optional[Dict[str, Any]]:

    response = (
        supabase
        .table("services")
        .select("*")
        .eq("service_id", service_id)
        .limit(1)
        .execute()
    )

    if response.data:
        return response.data[0]

    return None


# ============================================================
# ROUTE SEARCH
# ============================================================

def route_search(
    origin: str,
    destination: str
) -> List[Dict[str, Any]]:

    routes = get_all_routes()

    origin_lower = origin.lower().strip()
    destination_lower = destination.lower().strip()

    matches = []

    for route in routes:

        route_origin = str(
            route.get("origin") or ""
        ).lower().strip()

        route_destination = str(
            route.get("destination") or ""
        ).lower().strip()

        origin_match = (
            origin_lower in route_origin
            or route_origin in origin_lower
        )

        destination_match = (
            destination_lower in route_destination
            or route_destination in destination_lower
        )

        if origin_match and destination_match:
            matches.append(route)

    return matches


# ============================================================
# ROUTE INFORMATION
# ============================================================

def route_information(
    route_id: str
) -> Dict[str, Any]:

    route = get_route_by_id(route_id)

    if not route:

        return {
            "found": False,
            "message": (
                f"Route {route_id} was not found."
            )
        }

    stops = get_route_stops(route_id)

    return {
        "found": True,
        "route": route,
        "stops": stops,
        "stop_count": len(stops),
    }


# ============================================================
# SERVICE INFORMATION
# ============================================================

def service_information(
    service_id: Optional[str] = None
) -> Dict[str, Any]:

    if service_id:

        service = get_service_by_id(
            service_id
        )

        if not service:

            return {
                "found": False,
                "message": (
                    f"Service {service_id} "
                    "was not found."
                )
            }

        return {
            "found": True,
            "service": service,
        }

    return {
        "found": True,
        "services": get_services(),
    }


# ============================================================
# STOP INFORMATION
# ============================================================

def stop_information(
    stop_id: str
) -> Dict[str, Any]:

    stop = get_stop_by_id(stop_id)

    if not stop:

        return {
            "found": False,
            "message": (
                f"Stop {stop_id} was not found."
            )
        }

    routes = get_stop_routes(stop_id)

    return {
        "found": True,
        "stop": stop,
        "routes": routes,
    }


# ============================================================
# DATABASE HEALTH CHECK
# ============================================================

def database_health() -> Dict[str, Any]:

    try:

        routes = (
            supabase
            .table("routes")
            .select("route_id")
            .limit(1)
            .execute()
        )

        stops = (
            supabase
            .table("stops")
            .select("stop_id")
            .limit(1)
            .execute()
        )

        services = (
            supabase
            .table("services")
            .select("service_id")
            .limit(1)
            .execute()
        )

        return {
            "connected": True,
            "routes": len(routes.data or []),
            "stops": len(stops.data or []),
            "services": len(services.data or []),
        }

    except Exception as e:

        return {
            "connected": False,
            "error": str(e),
        }