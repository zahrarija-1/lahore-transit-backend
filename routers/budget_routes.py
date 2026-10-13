
import csv
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from auth import get_current_user
from db_tools import route_search
from supabase_client import get_supabase

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
    with open(FARES_FILE, encoding="utf-8-sig") as file:
        return list(csv.DictReader(file))


def get_service(route):
    value = " ".join(
        str(route.get(key) or "")
        for key in (
            "service_type", "route_type",
            "route_name", "name", "route_id"
        )
    ).lower()

    if "metrobus" in value or "metro bus" in value:
        return "metrobus"

    if "feeder" in value or "speedo" in value:
        return "feeder"

    if "orange" in value:
        return "orange"

    return None


def get_fare(route, fare_rows):
    service = get_service(route)

    if not service or service == "orange":
        return None

    for row in fare_rows:
        label = row.get("service_type", "").lower()
        rule = row.get("fare_rule", "").lower()

        if service not in label:
            continue

        if "single journey" not in rule:
            continue

        try:
            return float(row["fare_rs"])
        except (ValueError, TypeError, KeyError):
            continue

    return None


def save_record(table, data):
    response = (
        get_supabase()
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
        routes = route_search(
            request.origin.strip(),
            request.destination.strip()
        )

        fares = load_fares()
        journeys = 2 if request.return_trip else 1

        options = []

        for route in routes:
            fare = get_fare(route, fares)

            if fare is None:
                continue

            monthly_cost = round(
                fare * journeys * request.travel_days, 2
            )

            options.append({
                "route_name": str(
                    route.get("route_name")
                    or route.get("name")
                    or route.get("route_id")
                    or "Unknown Route"
                ),
                "bus_service": get_service(route),
                "fare_per_trip": fare,
                "daily_cost": fare * journeys,
                "monthly_cost": monthly_cost,
                "remaining_budget": round(
                    request.monthly_budget - monthly_cost, 2
                ),
                "within_budget": (
                    monthly_cost <= request.monthly_budget
                )
            })

        options.sort(key=lambda x: x["monthly_cost"])

        best = options[0] if options else None

        if best:
            if request.language.lower().startswith("ur"):
                reply = (
                    f"Aap ke liye {best['route_name']} "
                    f"ka estimated monthly kharcha "
                    f"Rs. {best['monthly_cost']:.0f} hai. "
                )
                if best["within_budget"]:
                    reply += (
                        f"Rs. {best['remaining_budget']:.0f} "
                        "budget mein bachenge."
                    )
                else:
                    reply += "Ye route aapke budget se zyada hai."
            else:
                reply = (
                    f"Best available direct option: "
                    f"{best['route_name']}. "
                    f"Estimated monthly cost: "
                    f"Rs. {best['monthly_cost']:.0f}. "
                )
                reply += (
                    "Within budget."
                    if best["within_budget"]
                    else "Over budget."
                )
        else:
            reply = (
                "Is route ke liye verified direct bus fare "
                "nahi mila. Starting point aur destination "
                "check karein."
                if request.language.lower().startswith("ur")
                else
                "No direct route with a calculable fare found."
            )

        budget = save_record("travel_budgets", {
            "user_id": user_id,
            "monthly_budget": request.monthly_budget,
            "travel_days": request.travel_days
        })

        commute = save_record("daily_commutes", {
            "user_id": user_id,
            "budget_id": budget["id"],
            "starting_point": request.origin.strip(),
            "destination": request.destination.strip(),
            "return_trip": request.return_trip,
            "travel_days": request.travel_days
        })

        if best:
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

        return {
            "reply": reply,
            "monthly_budget": request.monthly_budget,
            "best_route": best,
            "alternatives": options[1:5],
            "travel_days": request.travel_days,
            "notice": (
                "Estimates use stored fare reference data. "
                "Confirm current fares before travelling."
            )
        }

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Budget service unavailable"
        ) from exc


@router.get("/history")
def budget_history(
    user: dict = Depends(get_current_user)
):
    user_id = str(user["user_id"])

    try:
        supabase = get_supabase()

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

    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Budget history unavailable"
        ) from exc
