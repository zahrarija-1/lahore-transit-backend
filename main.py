from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from assistant import session
from assistant.graph_builder import get_graph
from assistant.pipeline import answer

from routers import auth_routes
from routers import transport_routes
from routers import nearby_routes


# ============================================================
# Application Lifespan
# ============================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Load the transit graph when Render starts the backend.
    """

    try:
        graph = get_graph(force_reload=True)

        print("========================================")
        print("Transit AI Backend Started")
        print("========================================")
        print(f"Stops loaded: {len(graph.stop_name)}")
        print(f"Routes loaded: {len(graph.route_info)}")
        print(
            f"Stops with coordinates: "
            f"{len(graph.stop_coordinates)}"
        )
        print("========================================")

    except Exception as exc:
        print("========================================")
        print("Transit graph loading error")
        print(f"Error: {exc}")
        print("========================================")

    yield


# ============================================================
# FastAPI App
# ============================================================

app = FastAPI(
    title="Transit AI API",
    description=(
        "Lahore Transit AI backend for authentication, "
        "transit routes, nearby stops and AI assistance."
    ),
    version="1.0.0",
    lifespan=lifespan,
)


# ============================================================
# CORS
# ============================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# Routers
# ============================================================

app.include_router(auth_routes.router)
app.include_router(transport_routes.router)
app.include_router(nearby_routes.router)


# ============================================================
# Chat Schemas
# ============================================================

class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None


class ChatResponse(BaseModel):
    response: str
    session_id: str


# ============================================================
# Root
# ============================================================

@app.get("/")
def root():
    return {
        "message": "Transit AI API is running",
        "status": "online",
        "docs": "/docs",
    }


# ============================================================
# Health
# ============================================================

@app.get("/health")
def health():
    try:
        graph = get_graph()

        return {
            "status": "healthy",
            "service": "Transit AI API",
            "stops": len(graph.stop_name),
            "routes": len(graph.route_info),
            "stops_with_coordinates": len(
                graph.stop_coordinates
            ),
        }

    except Exception as exc:
        return {
            "status": "degraded",
            "service": "Transit AI API",
            "error": str(exc),
        }


# ============================================================
# AI Chat
# ============================================================

@app.post(
    "/chat",
    response_model=ChatResponse,
)
def chat(request: ChatRequest):

    # Create a new session if needed
    session_id = request.session_id

    if not session_id:
        session_id = session.create_session()

    # Save user message
    session.add_message(
        session_id=session_id,
        role="user",
        content=request.message,
    )

    # Get previous conversation
    history = session.get_history(
        session_id
    )

    try:
        result = answer(
            request.message,
            history=history,
        )

        if isinstance(result, dict):
            response_text = (
                result.get("response")
                or result.get("answer")
                or result.get("message")
                or str(result)
            )
        else:
            response_text = str(result)

    except Exception as exc:
        response_text = (
            "Sorry, I could not process your request "
            "right now."
        )

        print(
            f"Chat processing error: {exc}"
        )

    # Save assistant response
    session.add_message(
        session_id=session_id,
        role="assistant",
        content=response_text,
    )

    return ChatResponse(
        response=response_text,
        session_id=session_id,
    )


# ============================================================
# Reset Chat
# ============================================================

@app.post("/chat/reset")
def reset_chat(
    session_id: str,
):
    try:
        session.clear_session(
            session_id
        )

        return {
            "success": True,
            "session_id": session_id,
            "message": "Chat session reset successfully.",
        }

    except Exception as exc:
        return {
            "success": False,
            "session_id": session_id,
            "message": str(exc),
        }