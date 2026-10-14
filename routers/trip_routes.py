from pydantic import BaseModel, Field, field_validator
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from auth import get_current_user
from supabase_client import supabase_admin


router = APIRouter(
    prefix="/trips",
    tags=["Trip History"]
)



class TripCreate(BaseModel):
    origin: str = Field(min_length=1)
    destination: str = Field(min_length=1)
    origin_id: Optional[str] = None
    destination_id: Optional[str] = None
    route_found: bool = False
    route_id: Optional[str] = None

    trip_status: str = "completed"
    fare: int = Field(default=0, ge=0)
    eta_minutes: int = Field(default=0, ge=0)
    transport_type: Optional[str] = None
    rating: Optional[int] = Field(default=None, ge=1, le=5)

    @field_validator("trip_status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        if value not in ("completed", "cancelled"):
            raise ValueError(
                "Status must be completed or cancelled"
            )
        return value



@router.post("", status_code=201)
def save_trip(
    request: TripCreate,
    current_user: dict = Depends(get_current_user)
):
    data = {
        "user_id": current_user["user_id"],
        **request.model_dump()
    }

    try:
        response = (
            supabase_admin
            .table("trip_history")
            .insert(data)
            .execute()
        )

        return {
            "message": "Trip saved successfully",
            "trip": response.data[0]
        }

    except Exception as exc:
        print("TRIP SAVE ERROR:", str(exc))
        raise HTTPException(
            status_code=500,
            detail="Unable to save trip."
        ) from exc


@router.get("")
def get_trips(
    current_user: dict = Depends(get_current_user)
):
    try:
        response = (
            supabase_admin
            .table("trip_history")
            .select("*")
            .eq("user_id", current_user["user_id"])
            .order("searched_at", desc=True)
            .execute()
        )

        return {"trips": response.data or []}

    except Exception as exc:
        print("TRIP FETCH ERROR:", str(exc))
        raise HTTPException(
            status_code=500,
            detail="Unable to load trips."
        ) from exc


@router.delete("/{trip_id}")
def delete_trip(
    trip_id: UUID,
    current_user: dict = Depends(get_current_user)
):
    try:
        response = (
            supabase_admin
            .table("trip_history")
            .delete()
            .eq("trip_id", str(trip_id))
            .eq("user_id", current_user["user_id"])
            .execute()
        )

        if not response.data:
            raise HTTPException(
                status_code=404,
                detail="Trip not found."
            )

        return {"message": "Trip deleted successfully"}

    except HTTPException:
        raise

    except Exception as exc:
        print("TRIP DELETE ERROR:", str(exc))
        raise HTTPException(
            status_code=500,
            detail="Unable to delete trip."
        ) from exc
