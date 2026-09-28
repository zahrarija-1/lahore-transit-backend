from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from assistant import session
from assistant.graph_builder import get_graph
from assistant.pipeline import answer
from routers import auth_routes, transport_routes


# ---------------------------------------------------------------------------
# Startup: build the graph once so the first request is not slow
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    graph = get_graph()
    print(f"Transit graph ready: {len(graph.stop_name)} stops, "
          f"{len(graph.stops_by_route)} routes with stop data")
    yield


app = FastAPI(
    title="Transit AI API",
    description="AI-powered Lahore Public Transport Assistant",
    version="2.0.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
# A Flutter web build runs inside a browser, and browsers block requests to
# a different address unless the server allows it. This grants that
# permission.
#
# allow_origins is "*" for development only. Before deployment it must be
# narrowed to the app's real address.

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
# Auth endpoints live in routers/auth_routes.py and transport endpoints in
# routers/transport_routes.py, so this file stays readable as the API grows.

app.include_router(auth_routes.router)
app.include_router(transport_routes.router)


# ---------------------------------------------------------------------------
# Schemas (what Flutter sends and receives)
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=500)
    session_id: str = Field("default", max_length=64)
    debug: bool = False


class ChatResponse(BaseModel):
    response: str
    intent: str
    data: dict | None = None      # structured facts, for map/list UI later


# ---------------------------------------------------------------------------
# System
# ---------------------------------------------------------------------------

@app.get("/", tags=["System"])
def root():
    return {"message": "Transit AI API is running", "status": "online"}


@app.get("/health", tags=["System"])
def health():
    graph = get_graph()
    return {
        "status": "healthy",
        "stops": len(graph.stop_name),
        "routes_with_stops": len(graph.stops_by_route),
        "transfer_stops": len(graph.transfer_stops()),
    }


# ---------------------------------------------------------------------------
# AI Assistant
# ---------------------------------------------------------------------------

@app.post("/chat", response_model=ChatResponse, tags=["AI Assistant"])
def chat(request: ChatRequest):
    result = answer(request.message, request.session_id)
    intent = result["intent"]
    return ChatResponse(
        response=result["response"],
        intent=intent["intent"] if isinstance(intent, dict) else str(intent),
        data=result["facts"] if request.debug else None,
    )


@app.post("/chat/reset", tags=["AI Assistant"])
def reset_chat(session_id: str = "default"):
    session.reset(session_id)
    return {"status": "cleared", "session_id": session_id}