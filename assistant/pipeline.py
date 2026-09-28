"""
The whole assistant in one function.

    user message
        -> intent_parser   (LLM #1: understand)
        -> session slots   (fill in what the user didn't repeat)
        -> handlers        (Python: all data + calculations)
        -> response_builder(LLM #2: phrase it)

Two LLM calls per message. Never more.
"""

from . import session
from .handlers import run_handler
from .intent_parser import parse_intent
from .response_builder import build_response


def answer(message, session_id="default"):
    message = (message or "").strip()
    if not message:
        return {"response": "Please type a question about Lahore transport.",
                "intent": "empty", "facts": {}}

    # 1. Understand
    intent = parse_intent(message, session_id)

    # 2. Fill gaps from memory ("aur sasti koi hai?" has no source/destination)
    slots = session.get_slots(session_id)
    if intent["intent"] in ("plan_route", "fare_info"):
        intent["source"] = intent.get("source") or slots.get("source")
        intent["destination"] = intent.get("destination") or slots.get("destination")

    # 3. Python does the work
    facts = run_handler(intent, message)

    # 4. Phrase it
    reply = build_response(message, facts, intent.get("language", "en"))

    # 5. Remember for the next turn
    session.update_slots(
        session_id,
        source=intent.get("source"),
        destination=intent.get("destination"),
        stop=intent.get("stop"),
        route_id=intent.get("route_id"),
    )
    session.add_turn(session_id, "user", message)
    session.add_turn(session_id, "assistant", reply)

    return {"response": reply, "intent": intent, "facts": facts}