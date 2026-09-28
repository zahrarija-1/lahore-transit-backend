"""
Routing engine: all transport calculations happen here.

The LLM never touches this file's numbers. It only receives the JSON
produced at the bottom of it.

FARE MODEL (from data/fares.csv, PMA official):
    Lahore Feeder Routes - Phase I : 1 journey Rs 20, 2 journeys Rs 25,
                                     3 journeys Rs 30
    Lahore Metrobus System         : Rs 30 single journey

So the fare depends on the NUMBER OF BOARDINGS, not on distance or on the
number of stops. That means "cheapest route" and "fewest transfers" are the
same optimisation on this network.

NOT SUPPORTED (data does not exist):
    - travel time      : no per-segment times in the dataset
    - distance         : stops.csv has no latitude/longitude
    - nearby stops     : same reason
"""

import heapq
from difflib import SequenceMatcher

from .graph_builder import get_graph, normalize

# Fare table for feeder journeys, keyed by number of boardings.
FEEDER_FARE_BY_JOURNEYS = {1: 20, 2: 25, 3: 30}
METROBUS_SINGLE_FARE = 30


# ---------------------------------------------------------------------------
# 1. Stop name resolution
# ---------------------------------------------------------------------------

def resolve_stop(name, limit=4):
    """
    Turn a user-typed stop name into candidate stops.

    Returns {"status": "exact"|"ambiguous"|"not_found", "matches": [...]}
    Matching is tolerant: exact -> substring -> fuzzy similarity, so
    "kalma", "Kalma chowk" and "kalma chok" all work.
    """
    graph = get_graph()
    query = normalize(name)
    if not query:
        return {"status": "not_found", "matches": []}

    # exact normalized match
    if query in graph.stop_ids_by_norm:
        ids = graph.stop_ids_by_norm[query]
        return {
            "status": "exact" if len(ids) == 1 else "ambiguous",
            "matches": [_stop_dict(i) for i in ids[:limit]],
        }

    scored = []
    for norm_name, ids in graph.stop_ids_by_norm.items():
        if query in norm_name or norm_name in query:
            score = 0.9
        else:
            score = SequenceMatcher(None, query, norm_name).ratio()
        if score >= 0.62:
            for stop_id in ids:
                scored.append((score, stop_id))

    if not scored:
        return {"status": "not_found", "matches": []}

    scored.sort(key=lambda x: (-x[0], graph.name_of(x[1])))
    top_score = scored[0][0]
    matches = [_stop_dict(i) for _, i in scored[:limit]]

    # Confident single winner
    if len(scored) == 1 or top_score - scored[1][0] > 0.12:
        return {"status": "exact", "matches": matches[:1]}
    return {"status": "ambiguous", "matches": matches}


def _stop_dict(stop_id):
    graph = get_graph()
    return {
        "stop_id": stop_id,
        "stop_name": graph.name_of(stop_id),
        "routes": sorted(graph.routes_by_stop.get(stop_id, [])),
    }


# ---------------------------------------------------------------------------
# 2. Shortest path (Dijkstra over stop + current-route states)
# ---------------------------------------------------------------------------

def _search(source_id, destination_id, weight):
    """
    Dijkstra where a state is (stop_id, route currently being ridden).

    weight(is_new_boarding) returns a (primary, secondary) cost tuple, which
    lets the same function optimise either "fewest boardings" or
    "fewest stops" without duplicating the algorithm.
    """
    graph = get_graph()
    start = (source_id, None)
    best = {start: (0, 0)}
    previous = {}
    queue = [((0, 0), source_id, None)]

    while queue:
        cost, stop_id, route_id = heapq.heappop(queue)
        if cost > best.get((stop_id, route_id), (float("inf"),) * 2):
            continue
        if stop_id == destination_id:
            return _rebuild(previous, (stop_id, route_id), source_id)

        for neighbour, edge_route in graph.neighbours(stop_id):
            boarding = edge_route != route_id
            step = weight(boarding)
            new_cost = (cost[0] + step[0], cost[1] + step[1])
            state = (neighbour, edge_route)
            if new_cost < best.get(state, (float("inf"),) * 2):
                best[state] = new_cost
                previous[state] = (stop_id, route_id)
                heapq.heappush(queue, (new_cost, neighbour, edge_route))

    return None


def _rebuild(previous, end_state, source_id):
    """Walk the predecessor map backwards into an ordered list of states."""
    path = [end_state]
    while path[-1] in previous:
        path.append(previous[path[-1]])
    path.reverse()
    if path[0][0] != source_id:
        return None
    return path


# ---------------------------------------------------------------------------
# 3. Turning a path into segments + fare
# ---------------------------------------------------------------------------

def _to_journey(path):
    """Group consecutive states that use the same route into segments."""
    graph = get_graph()
    segments = []

    for stop_id, route_id in path[1:]:
        if segments and segments[-1]["route_id"] == route_id:
            segments[-1]["to_stop"] = graph.name_of(stop_id)
            segments[-1]["to_stop_id"] = stop_id
            segments[-1]["stops"] += 1
        else:
            previous_stop = (
                segments[-1]["to_stop_id"] if segments else path[0][0]
            )
            info = graph.route_info.get(route_id, {})
            segments.append({
                "route_id": route_id,
                "system": info.get("system", "Unknown"),
                "route_type": info.get("route_type", "Unknown"),
                "from_stop": graph.name_of(previous_stop),
                "from_stop_id": previous_stop,
                "to_stop": graph.name_of(stop_id),
                "to_stop_id": stop_id,
                "stops": 1,
            })

    fare = _fare_for_segments(segments)
    return {
        "segments": segments,
        "boardings": len(segments),
        "transfers": max(len(segments) - 1, 0),
        "total_stops": sum(s["stops"] for s in segments),
        **fare,
    }


def _fare_for_segments(segments):
    """
    Apply the real PMA fare rules: feeder fare is tiered by number of
    journeys; Metrobus is charged per single journey.
    """
    feeder = sum(1 for s in segments if s["route_type"] == "Feeder")
    metrobus = sum(1 for s in segments if s["route_type"] == "Metrobus")

    total = 0
    exact = True
    notes = []

    if feeder:
        if feeder in FEEDER_FARE_BY_JOURNEYS:
            total += FEEDER_FARE_BY_JOURNEYS[feeder]
        else:
            total += FEEDER_FARE_BY_JOURNEYS[3]
            exact = False
            notes.append(
                f"Fare data only covers up to 3 feeder journeys; this trip "
                f"needs {feeder}, so the real fare may be higher."
            )
    if metrobus:
        total += METROBUS_SINGLE_FARE * metrobus

    return {
        "total_fare_rs": total,
        "fare_is_exact": exact,
        "fare_basis": (
            f"{feeder} feeder journey(s)"
            + (f" + {metrobus} Metrobus journey(s)" if metrobus else "")
        ),
        "fare_notes": notes,
    }


# ---------------------------------------------------------------------------
# 4. Public entry point
# ---------------------------------------------------------------------------

def plan_route(source_name, destination_name):
    """
    Plan a trip between two stop names.

    Always returns a dict with "status". The assistant layer decides what to
    say; this function never produces prose.
    """
    source = resolve_stop(source_name)
    destination = resolve_stop(destination_name)

    if source["status"] == "not_found":
        return {"status": "source_not_found", "query": source_name}
    if destination["status"] == "not_found":
        return {"status": "destination_not_found", "query": destination_name}
    if source["status"] == "ambiguous":
        return {"status": "source_ambiguous", "query": source_name,
                "options": source["matches"]}
    if destination["status"] == "ambiguous":
        return {"status": "destination_ambiguous", "query": destination_name,
                "options": destination["matches"]}

    source_stop = source["matches"][0]
    destination_stop = destination["matches"][0]

    if source_stop["stop_id"] == destination_stop["stop_id"]:
        return {"status": "same_stop", "stop": source_stop["stop_name"]}

    # Primary: fewest boardings (= cheapest, given the fare rules)
    cheapest = _search(
        source_stop["stop_id"], destination_stop["stop_id"],
        weight=lambda boarding: (1 if boarding else 0, 1),
    )
    if cheapest is None:
        return {
            "status": "no_route",
            "source": source_stop["stop_name"],
            "destination": destination_stop["stop_name"],
        }

    journeys = [_to_journey(cheapest)]

    # Alternative: fewest stops (may ride further but change more often)
    fewest_stops = _search(
        source_stop["stop_id"], destination_stop["stop_id"],
        weight=lambda boarding: (1, 1 if boarding else 0),
    )
    if fewest_stops:
        alternative = _to_journey(fewest_stops)
        if _route_sequence(alternative) != _route_sequence(journeys[0]):
            journeys.append(alternative)

    journeys.sort(key=lambda j: (j["total_fare_rs"], j["total_stops"]))

    return {
        "status": "ok",
        "source": source_stop["stop_name"],
        "destination": destination_stop["stop_name"],
        "journeys": journeys,
        "coverage_note": (
            "Route planning covers the 15 Lahore feeder routes in the "
            "dataset. Metrobus and Orange Line station lists are not "
            "available, so they are not included in path finding."
        ),
    }


def _route_sequence(journey):
    return tuple(s["route_id"] for s in journey["segments"])


if __name__ == "__main__":
    import json
    for a, b in [("Kalma Chowk", "Railway Station"),
                 ("kalma", "chuburji"),
                 ("Bhatti Chowk", "R.A Bazar"),
                 ("nowhere place", "Liberty")]:
        print(f"\n===== {a} -> {b} =====")
        print(json.dumps(plan_route(a, b), indent=2)[:1400])