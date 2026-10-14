
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from auth import get_current_user
from supabase_client import supabase_admin

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/traveller-chat",
    tags=["Travellers Live Chat"]
)


class ChatMessageRequest(BaseModel):
    message: str = Field(min_length=1, max_length=500)


@router.get("/messages")
def get_messages(
    limit: int = Query(default=50, ge=1, le=100),
    user: dict = Depends(get_current_user)
):
    try:
        result = (
            supabase_admin
            .table("traveller_messages")
            .select("id,user_id,sender_name,message,created_at")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )

        messages = result.data or []
        messages.reverse()

        return {"messages": messages}

    except Exception:
        logger.exception("Failed to load traveller messages")
        raise HTTPException(
            status_code=503,
            detail="Unable to load chat messages"
        )


@router.post("/messages", status_code=201)
def send_message(
    request: ChatMessageRequest,
    user: dict = Depends(get_current_user)
):
    message = request.message.strip()

    if not message:
        raise HTTPException(
            status_code=422,
            detail="Message cannot be empty"
        )

    user_id = str(user["user_id"])

    # A temporary display name until profile-name mapping is verified.
    sender_name = "Traveller-" + user_id[:8]

    try:
        result = (
            supabase_admin
            .table("traveller_messages")
            .insert({
                "user_id": user_id,
                "sender_name": sender_name,
                "message": message
            })
            .execute()
        )

        if not result.data:
            raise RuntimeError("Message was not saved")

        return {
            "success": True,
            "message": result.data[0]
        }

    except Exception:
        logger.exception("Failed to send traveller message")
        raise HTTPException(
            status_code=503,
            detail="Unable to send chat message"
        )
