"""
Transit AI - AI assistant endpoint.

POST /chat

The agent is imported inside the function, not at the top of this
file. Importing agent.py pulls in rag.py, which loads the embedding
model and builds the FAISS index. That takes time. Doing it at import
time would mean the whole server waits for it before it can serve a
single request, including /health and /auth/login.

Loading it on the first chat request instead means the server starts
immediately, and only the first chat user waits.
"""

import logging

from fastapi import APIRouter, HTTPException, status

from schemas import ChatRequest, ChatResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["AI Assistant"])

# Holds the agent function once it has been loaded.
_agent = None


def get_agent():
    """Import the agent on first use, then reuse it."""

    global _agent

    if _agent is None:
        logger.info("Loading Transit AI agent (first request)...")

        from agent import transit_agent

        _agent = transit_agent
        logger.info("Transit AI agent ready.")

    return _agent


@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    """Ask the Transit AI assistant a question."""

    message = request.message.strip()

    if not message:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Message cannot be empty."
        )

    try:
        agent = get_agent()
        answer = agent(message)

    except Exception as exc:
        logger.exception("Chat request failed")

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "The Transit AI assistant is temporarily unavailable. "
                "Please try again."
            )
        ) from exc

    if not answer:
        answer = (
            "I could not produce an answer for that. "
            "Please try rephrasing your question."
        )

    return {"response": answer}