
from __future__ import annotations

import time
import logging

from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from assistant import session
from assistant.graph_builder import get_graph

from routers import auth_routes
from routers import transport_routes
from routers import nearby_routes
from routers import budget_routes
from routers import trip_routes


# ============================================================
# Logging Configuration
# ============================================================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============================================================
# Application Lifespan
# ============================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start HTTP promptly; graph loads on first request that needs it."""
    logger.info("Transit AI startup: graph loading deferred until needed")
    yield
    logger.info("Transit AI Backend Shutting Down")


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
app.include_router(budget_routes.router)
app.include_router(trip_routes.router)


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
        logger.exception("Health check graph error")

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

    session_id = request.session_id or "default"

    try:
        # Load assistant modules only when chat is actually requested.
        from assistant.pipeline import answer

        result = answer(
            request.message,
            session_id=session_id,
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

    except Exception:
        logger.exception("Chat processing error")

        response_text = (
            "Sorry, I could not process your request "
            "right now."
        )

    return ChatResponse(
        response=response_text,
        session_id=session_id,
    )


# ============================================================
# Reset Chat
# ============================================================

@app.post("/chat/reset")
def reset_chat(session_id: str):

    try:
        session.reset(session_id)

        return {
            "success": True,
            "session_id": session_id,
            "message": "Chat session reset successfully.",
        }

    except Exception as exc:
        logger.exception("Chat reset error")

        return {
            "success": False,
            "session_id": session_id,
            "message": str(exc),
        }
