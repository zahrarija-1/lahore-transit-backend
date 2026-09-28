"""
One handler per intent. This is where Python does the real work.

Every handler returns a plain dict of verified facts taken from the
database. Nothing here writes sentences, and nothing here calls the LLM.
"""

import os
import sqlite3

from .graph_builder import get_graph
from .routing_engine import plan_route, resolve_stop

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "transit_ai.db")


def _query(sql, params=()):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# plan_route
# ---------------------------------------------------------------------------

def handle_plan_route(intent):
    source = intent.get("source")
    destination = intent.get("destination")

    missing = [n for n, v in (("source", source), ("destination", destination))
               if not v]
    if missing:
        return {"kind": "needs_info", "missing": missing}

    result = plan_route(source, destination)

    if result["status"] == "ok" and intent.get("preference") == "fewest_transfers":
        result["journeys"].sort(key=lambda j: (j["transfers"], j["total_fare_rs"]))

    return {"kind": "route_result", **result}


# ---------------------------------------------------------------------------
# stop_info
# ---------------------------------------------------------------------------

def handle_stop_info(intent):
    name = intent.get("stop") or intent.get("source") or intent.get("destination")
    if not name:
        return {"kind": "needs_info", "missing": ["stop"]}

    found = resolve_stop(name)
    if found["status"] == "not_found":
        return {"kind": "stop_not_found", "query": name}
    if found["status"] == "ambiguous":
        return {"kind": "stop_ambiguous", "query": name,
                "options": found["matches"]}

    stop = found["matches"][0]
    graph = get_graph()
    routes = []
    for route_id in stop["routes"]:
        info = graph.route_info.get(route_id, {})
        routes.append({
            "route_id": route_id,
            "origin": info.get("origin"),
            "destination": info.get("destination"),
            "fare_rs": info.get("fare_rs"),
            "operating_hours": info.get("operating_hours"),
        })

    return {
        "kind": "stop_info",
        "stop_name": stop["stop_name"],
        "stop_id": stop["stop_id"],
        "routes": routes,
        "is_transfer_point": len(routes) > 1,
    }


# ---------------------------------------------------------------------------
# route_info
# ---------------------------------------------------------------------------

def handle_route_info(intent):
    route_id = intent.get("route_id")
    if not route_id:
        return {"kind": "needs_info", "missing": ["route_id"]}

    graph = get_graph()
    info = graph.route_info.get(route_id)
    if not info:
        return {"kind": "route_not_found", "query": route_id,
                "available_routes": sorted(graph.route_info)}

    stop_ids = graph.stops_by_route.get(route_id, [])
    return {
        "kind": "route_info",
        "route_id": route_id,
        "system": info.get("system"),
        "origin": info.get("origin"),
        "destination": info.get("destination"),
        "fare_rs": info.get("fare_rs"),
        "operating_hours": info.get("operating_hours"),
        "stop_count": len(stop_ids) or info.get("stop_count"),
        "stops": [graph.name_of(s) for s in stop_ids],
        "stop_list_available": bool(stop_ids),
    }


# ---------------------------------------------------------------------------
# fare_info / timing_info
# ---------------------------------------------------------------------------

def handle_fare_info(intent):
    # If the user named both ends, a real calculated fare beats a fare table.
    if intent.get("source") and intent.get("destination"):
        return handle_plan_route(intent)
    return {"kind": "fare_table",
            "fares": _query("SELECT service_type, fare_rule, fare_rs, currency "
                            "FROM fares")}


def handle_timing_info(intent):
    return {
        "kind": "timings",
        "services": _query("SELECT service, operating_hours, headway "
                           "FROM services"),
    }


# ---------------------------------------------------------------------------
# faq (RAG)
# ---------------------------------------------------------------------------

def handle_faq(intent, message):
    try:
        from rag import search_transit_knowledge          # heavy import
        results = search_transit_knowledge(message, top_k=3)
    except Exception as error:                            # index not built yet
        return {"kind": "faq_unavailable", "reason": str(error)[:200],
                "fallback": _query("SELECT question, answer, source_url "
                                   "FROM transit_faq")}

    return {"kind": "faq", "results": results}


# ---------------------------------------------------------------------------
# greeting / capabilities
# ---------------------------------------------------------------------------

def handle_greeting(intent):
    graph = get_graph()
    return {
        "kind": "capabilities",
        "can_do": [
            "plan a trip between two feeder-route stops",
            "tell which routes serve a stop",
            "list the stops on a route",
            "give official fares and operating hours",
            "answer general questions from the transit FAQ",
        ],
        "cannot_do": [
            "live bus locations or arrival times (no live data source)",
            "travel time estimates (not in the dataset)",
            "nearby stops (stop coordinates are missing)",
            "Metrobus / Orange Line station-level trip planning "
            "(station lists not in the dataset)",
        ],
        "coverage": {
            "routes_with_stop_data": len(graph.stops_by_route),
            "stops": len(graph.stop_name),
        },
    }


def handle_out_of_scope(intent):
    return {"kind": "out_of_scope"}


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

def run_handler(intent, message):
    mapping = {
        "plan_route": lambda: handle_plan_route(intent),
        "stop_info": lambda: handle_stop_info(intent),
        "route_info": lambda: handle_route_info(intent),
        "fare_info": lambda: handle_fare_info(intent),
        "timing_info": lambda: handle_timing_info(intent),
        "faq": lambda: handle_faq(intent, message),
        "greeting": lambda: handle_greeting(intent),
        "out_of_scope": lambda: handle_out_of_scope(intent),
    }
    return mapping.get(intent["intent"], mapping["faq"])()