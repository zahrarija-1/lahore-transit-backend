import csv
import logging
from pathlib import Path
from supabase_client import supabase_admin
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/budget-ai",
    tags=["AI Budget Assistant"]
)

FARES_FILE = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "fares.csv"
)


class BudgetRequest(BaseModel):
    monthly_budget: float = Field(gt=0)
    origin: str = Field(min_length=2)
    destination: str = Field(min_length=2)
    travel_days: int = Field(default=26, ge=1, le=31)
    return_trip: bool = True
    language: str = "en"


def load_fares():
    with open(FARES_FILE, encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def _norm(value):
    import re
    return " ".join(re.findall(r"[a-z0-9]+", str(value).lower()))


def _read_csv(filename):
    with open(FARES_FILE.parent / filename, encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def _stop_candidates(query, stop_names):
    """Exact/partial match; a unique first-word alias handles Liberty Market/Chowk."""
    q = _norm(query)
    if not q:
        return set()
    exact = {name for name in stop_names if _norm(name) == q}
    if exact:
        return exact
    partial = {name for name in stop_names if q in _norm(name) or _norm(name) in q}
    if partial:
        return partial
    first = q.split()[0]
    candidates = {name for name in stop_names if _norm(name).split()[0] == first}
    return candidates if len(candidates) == 1 else set()


def _service(route):
    label = _norm(" ".join(str(route.get(k) or "") for k in
                           ("route_type", "system", "route_id")))
    if "metrobus" in label or "metro bus" in label:
        return "metrobus"
    if "feeder" in label or "speedo" in label:
        return "feeder"
    if "orange" in label:
        return "orange"
    return None


def _single_fare(route, fares):
    service = _service(route)
    if service not in ("metrobus", "feeder"):
        return None
    for row in fares:
        label = _norm(row.get("service_type", ""))
        if service == "metrobus" and "metrobus" not in label and "metro bus" not in label:
            continue
        if service == "feeder" and "feeder" not in label:
            continue
        if _norm(row.get("fare_rule", "")) != "single journey":
            continue
        try:
            return float(row["fare_rs"])
        except (ValueError, TypeError, KeyError):
            continue
    return None


def find_budget_journeys(origin, destination, fares, max_legs=3):
    """Search only CSV-supported stops and forward ordered route segments."""
    from collections import defaultdict, deque
    routes = {r["route_id"]: r for r in _read_csv("routes.csv")}
    ordered = defaultdict(list)
    for item in _read_csv("route_stops.csv"):
        if item["route_id"] in routes:
            ordered[item["route_id"]].append(item)
    edges = defaultdict(list)
    names = set()
    for route_id, items in ordered.items():
        items.sort(key=lambda item: int(item["stop_sequence"]))
        fare = _single_fare(routes[route_id], fares)
        if fare is None:
            continue
        for i, boarding in enumerate(items):
            start = _norm(boarding["stop_name"])
            names.add(boarding["stop_name"])
            for arrival in items[i + 1:]:
                end = _norm(arrival["stop_name"])
                names.add(arrival["stop_name"])
                if start != end:
                    edges[start].append((end, route_id, boarding["stop_name"],
                                         arrival["stop_name"], fare))
    starts = {_norm(s) for s in _stop_candidates(origin, names)}
    ends = {_norm(s) for s in _stop_candidates(destination, names)}
    if not starts or not ends:
        return []
    queue = deque((s, [], frozenset([s])) for s in starts)
    found = []
    while queue:
        current, legs, visited = queue.popleft()
        if current in ends and legs:
            found.append(legs)
            continue
        if len(legs) >= max_legs:
            continue
        for nxt, rid, board, alight, fare in edges.get(current, []):
            if nxt in visited:
                continue
            # Prevent unnecessary reboarding of the same route.
            if any(l["route_id"] == rid for l in legs):
                continue
            new_leg = {"route_id": rid, "from": board, "to": alight,
                       "fare": fare, "service": _service(routes[rid])}
            queue.append((nxt, legs + [new_leg], visited | {nxt}))
    # Avoid duplicate paths; prioritize low fares then fewer transfers.
    found.sort(key=lambda path: (sum(leg["fare"] for leg in path), len(path)))
    unique = []
    seen = set()
    for legs in found:
        key = tuple((l["route_id"], _norm(l["from"]), _norm(l["to"])) for l in legs)
        if key not in seen:
            seen.add(key)
            unique.append(legs)
        if len(unique) >= 5:
            break
    return unique


def save_record(table, data):
    response = (
        supabase_admin
        .table(table)
        .insert(data)
        .execute()
    )

    if not response.data:
        raise RuntimeError("Database insert failed")

    return response.data[0]


@router.post("/recommend")
def recommend(
    request: BudgetRequest,
    user: dict = Depends(get_current_user)
):
    if request.origin.strip().lower() == request.destination.strip().lower():
        raise HTTPException(
            status_code=422,
            detail="Starting point and destination must differ"
        )

    user_id = str(user["user_id"])

    try:
        logger.info("Budget AI: finding stop-based journeys")
        fares = load_fares()
        journeys = find_budget_journeys(
            request.origin.strip(), request.destination.strip(), fares
        )
        trip_multiplier = 2 if request.return_trip else 1
        options = []
        for legs in journeys:
            one_way = sum(leg["fare"] for leg in legs)
            daily = round(one_way * trip_multiplier, 2)
            monthly = round(daily * request.travel_days, 2)
            route_names = " + ".join(leg["route_id"] for leg in legs)
            options.append({
                "route_name": route_names,
                "bus_service": " + ".join(leg["service"] for leg in legs),
                "fare_per_trip": round(one_way, 2),
                "daily_cost": daily,
                "monthly_cost": monthly,
                "remaining_budget": round(request.monthly_budget - monthly, 2),
                "within_budget": monthly <= request.monthly_budget,
                "legs": legs,
                "transfers": len(legs) - 1,
            })
        best = options[0] if options else None
        if best:
            if request.language.lower().startswith("ur"):
                reply = (
                    f"{best['route_name']} ke liye ek taraf ka kiraya Rs. "
                    f"{best['fare_per_trip']:.0f}, rozana Rs. {best['daily_cost']:.0f} "
                    f"aur {request.travel_days} din ka kharcha Rs. "
                    f"{best['monthly_cost']:.0f} hai. "
                )
                reply += ("Budget mein hai." if best["within_budget"]
                          else "Budget se zyada hai.")
            else:
                reply = (
                    f"Best available route: {best['route_name']} "
                    f"({best['transfers']} transfers). "
                    f"One-way Rs. {best['fare_per_trip']:.0f}, "
                    f"daily Rs. {best['daily_cost']:.0f}, "
                    f"monthly Rs. {best['monthly_cost']:.0f}. "
                    + ("Within budget." if best["within_budget"] else "Over budget.")
                )
        else:
            reply = (
                "Is safar ke liye available dataset mein connected route "
                "aur fare nahi mila."
                if request.language.lower().startswith("ur") else
                "No supported journey found in the available route and fare data."
            )

        logger.info("Budget AI: saving travel budget")
        budget = save_record("travel_budgets", {
            "user_id": user_id,
            "monthly_budget": request.monthly_budget,
            "travel_days": request.travel_days
        })

        logger.info("Budget AI: saving daily commute")
        commute = save_record("daily_commutes", {
            "user_id": user_id,
            "budget_id": budget["id"],
            "starting_point": request.origin.strip(),
            "destination": request.destination.strip(),
            "return_trip": request.return_trip,
            "travel_days": request.travel_days
        })

        if best:
            logger.info("Budget AI: saving recommendation")
            save_record("budget_recommendations", {
                "user_id": user_id,
                "commute_id": commute["id"],
                "recommended_bus": best["bus_service"],
                "recommended_route": best["route_name"],
                "fare_per_trip": best["fare_per_trip"],
                "estimated_monthly_cost": best["monthly_cost"],
                "monthly_budget": request.monthly_budget,
                "remaining_budget": best["remaining_budget"],
                "within_budget": best["within_budget"],
                "ai_explanation": reply
            })

        logger.info("Budget AI: recommendation completed successfully")
        return {
            "reply": reply,
            "monthly_budget": request.monthly_budget,
            "best_route": best,
            "alternatives": options[1:5],
            "travel_days": request.travel_days,
            "notice": (
                "Estimates use stored route-stop and fare data. "
                "Only listed services and forward stop order are supported; "
                "return travel assumes the same fare in reverse. "
                "Confirm routes and current fares before travelling."
            )
        }

    except HTTPException:
        raise
    except Exception:
        logger.exception("Budget AI recommendation failed")
        raise HTTPException(
            status_code=503,
            detail="Budget service unavailable"
        )


@router.get("/history")
def budget_history(
    user: dict = Depends(get_current_user)
):
    user_id = str(user["user_id"])

    try:
        supabase = supabase_admin

        return {
            "budgets": (
                supabase.table("travel_budgets")
                .select("*")
                .eq("user_id", user_id)
                .order("created_at", desc=True)
                .limit(30)
                .execute().data or []
            ),
            "commutes": (
                supabase.table("daily_commutes")
                .select("*")
                .eq("user_id", user_id)
                .order("created_at", desc=True)
                .limit(30)
                .execute().data or []
            ),
            "recommendations": (
                supabase.table("budget_recommendations")
                .select("*")
                .eq("user_id", user_id)
                .order("created_at", desc=True)
                .limit(30)
                .execute().data or []
            )
        }

    except Exception:
        logger.exception("Budget AI history failed")
        raise HTTPException(
            status_code=503,
            detail="Budget history unavailable"
        )
