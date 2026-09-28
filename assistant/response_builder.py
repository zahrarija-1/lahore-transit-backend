"""
LLM call #2 - phrase the reply.

The model receives ONLY the verified facts produced by handlers.py and is
told it may not add anything. If the model is unavailable, template_reply()
produces a plain reply from the same facts, so the API never fails just
because the LLM did.
"""

import json

from .llm import LLMUnavailable, complete

LANGUAGE_INSTRUCTION = {
    "en": "Reply in simple English.",
    "roman_urdu": "Reply in Roman Urdu (Urdu written in English letters).",
    "urdu": "Reply in Urdu script.",
}

SYSTEM_PROMPT = """You are Transit AI, an assistant for Lahore public transport.

You will be given FACTS as JSON. Write a short, friendly reply using ONLY
those facts.

Absolute rules:
- Never invent a stop, route, fare, timing or travel duration.
- Use the exact numbers and names in FACTS. Do not recalculate anything.
- Never state a travel time or distance; that data does not exist.
- If FACTS says information is missing or not found, say so plainly and
  suggest what the user can ask instead.
- Maximum 6 short lines. No markdown tables, no bullet symbols other than
  a simple dash.
- Mention a transfer clearly when there is one ("change at X").
"""


def build_response(message, facts, language="en"):
    """Turn verified facts into a sentence. Falls back to a template."""
    prompt = (
        f"User message: {message}\n\n"
        f"FACTS (the only information you may use):\n"
        f"{json.dumps(facts, ensure_ascii=False, indent=2)}\n\n"
        f"{LANGUAGE_INSTRUCTION.get(language, LANGUAGE_INSTRUCTION['en'])}"
    )
    try:
        reply = complete(SYSTEM_PROMPT, prompt, temperature=0.3, max_tokens=400)
        return reply or template_reply(facts)
    except LLMUnavailable:
        return template_reply(facts)


# ---------------------------------------------------------------------------
# Deterministic fallback - no LLM involved
# ---------------------------------------------------------------------------

def template_reply(facts):
    kind = facts.get("kind")

    if kind == "route_result":
        return _route_text(facts)

    if kind == "needs_info":
        missing = " and ".join(facts["missing"]).replace("_", " ")
        return f"I need the {missing} to plan this trip. Which stop do you mean?"

    if kind in ("stop_ambiguous", "route_ambiguous"):
        names = ", ".join(o["stop_name"] for o in facts.get("options", []))
        return f"I found more than one match for '{facts['query']}': {names}. Which one?"

    if kind == "stop_not_found":
        return (f"'{facts['query']}' is not in my stop list. "
                "It may not be on the 15 feeder routes I cover.")

    if kind == "stop_info":
        routes = ", ".join(
            f"{r['route_id']} ({r['origin']} - {r['destination']})"
            for r in facts["routes"]
        )
        return f"{facts['stop_name']} is served by: {routes}."

    if kind == "route_info":
        return (f"{facts['route_id']}: {facts['origin']} to "
                f"{facts['destination']}, {facts['stop_count']} stops, "
                f"Rs {facts['fare_rs']}, runs {facts['operating_hours']}.")

    if kind == "route_not_found":
        return (f"I don't have a route called {facts['query']}. "
                f"Available: {', '.join(facts['available_routes'])}.")

    if kind == "fare_table":
        lines = [f"- {f['service_type']}, {f['fare_rule']}: Rs {f['fare_rs']}"
                 for f in facts["fares"]]
        return "Official fares:\n" + "\n".join(lines)

    if kind == "timings":
        lines = [f"- {s['service']}: {s['operating_hours']}"
                 for s in facts["services"]]
        return "Operating hours:\n" + "\n".join(lines)

    if kind == "faq":
        results = facts.get("results") or []
        if not results:
            return "I don't have verified information about that yet."
        top = results[0]
        return top.get("text") or top.get("answer") or str(top)

    if kind == "faq_unavailable":
        return ("My FAQ search isn't ready. You can ask me about routes, "
                "stops, fares or timings instead.")

    if kind == "capabilities":
        can = "\n".join(f"- {c}" for c in facts["can_do"])
        return ("I'm Transit AI, for Lahore public transport. I can:\n"
                f"{can}\nTry: 'Kalma Chowk se Railway Station kaise jaun?'")

    if kind == "out_of_scope":
        return ("I only handle Lahore public transport - routes, stops, "
                "fares and timings.")

    return "I don't have verified information about that."


def _route_text(facts):
    if facts["status"] == "source_not_found":
        return f"I couldn't find a stop called '{facts['query']}'."
    if facts["status"] == "destination_not_found":
        return f"I couldn't find a destination called '{facts['query']}'."
    if facts["status"] in ("source_ambiguous", "destination_ambiguous"):
        names = ", ".join(o["stop_name"] for o in facts["options"])
        return f"Did you mean: {names}?"
    if facts["status"] == "same_stop":
        return f"That's the same stop ({facts['stop']})."
    if facts["status"] == "no_route":
        return (f"I couldn't find a connection from {facts['source']} to "
                f"{facts['destination']} on the feeder routes I cover.")

    lines = []
    for index, journey in enumerate(facts["journeys"][:2], start=1):
        steps = " then ".join(
            f"{s['route_id']} from {s['from_stop']} to {s['to_stop']} "
            f"({s['stops']} stops)"
            for s in journey["segments"]
        )
        label = "Best option" if index == 1 else "Alternative"
        lines.append(
            f"{label}: {steps}. Total Rs {journey['total_fare_rs']}, "
            f"{journey['transfers']} transfer(s)."
        )
    return "\n".join(lines)