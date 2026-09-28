"""
LLM call #1 - understand the sentence.

Input : raw user message + recent conversation
Output: structured JSON. No database access, no calculations.

Supporting 8 intents instead of 2 is what removes the "it only does one
thing" feeling. Passing the conversation history is what makes follow-ups
like "aur sasti koi hai?" or "wahan se Chuburji?" work.
"""

import re

from . import session
from .llm import LLMUnavailable, complete_json

INTENTS = [
    "plan_route",     # get me from A to B
    "stop_info",      # which buses stop at X
    "route_info",     # which stops does FRT09 cover
    "fare_info",      # what does it cost
    "timing_info",    # operating hours / headway
    "faq",            # general question answered from the FAQ knowledge base
    "greeting",       # hello / what can you do
    "out_of_scope",   # not about Lahore public transport
]

SYSTEM_PROMPT = f"""You extract structured meaning from messages sent to a \
Lahore public transport assistant. Users write in English, Urdu or Roman Urdu.

Return ONLY a JSON object, no explanation, with exactly these keys:
{{
  "intent": one of {INTENTS},
  "source": stop name the user is travelling FROM, or null,
  "destination": stop name the user is travelling TO, or null,
  "stop": a single stop the user asks about, or null,
  "route_id": a route code like FRT09 or LMB-L1, or null,
  "preference": "cheapest" or "fewest_transfers" or null,
  "language": "en" or "roman_urdu" or "urdu"
}}

Rules:
- Copy stop names exactly as the user wrote them. Do not translate,
  correct or complete them.
- "sasta", "sasti", "cheap" -> preference "cheapest".
- "kam transfer", "direct", "bina change" -> preference "fewest_transfers".
- If the message continues an earlier trip (e.g. "aur koi option?",
  "wahan se X?"), reuse the previous source/destination from the
  conversation unless the user clearly gives new ones.
- If the user only greets you or asks what you can do -> "greeting".
- If it is not about public transport in Lahore -> "out_of_scope".
- Never invent a stop name that the user did not mention."""


def parse_intent(message, session_id):
    """Return the intent dict. Falls back to rules if the model fails."""
    context = (
        f"Conversation so far:\n{session.history_as_text(session_id)}\n\n"
        f"Known so far: {session.get_slots(session_id)}\n\n"
        f"New user message: {message}"
    )

    try:
        data = complete_json(SYSTEM_PROMPT, context)
        return _clean(data, message)
    except LLMUnavailable:
        return _rule_based(message)


def _clean(data, message):
    """Never trust model output directly - validate every field."""
    def text(key):
        value = data.get(key)
        if isinstance(value, str) and value.strip().lower() not in ("", "null", "none"):
            return value.strip()
        return None

    intent = data.get("intent")
    if intent not in INTENTS:
        intent = "faq"

    route_id = text("route_id")
    if route_id:
        route_id = route_id.upper().replace(" ", "")

    preference = data.get("preference")
    if preference not in ("cheapest", "fewest_transfers"):
        preference = None

    language = data.get("language")
    if language not in ("en", "roman_urdu", "urdu"):
        language = _detect_language(message)

    return {
        "intent": intent,
        "source": text("source"),
        "destination": text("destination"),
        "stop": text("stop"),
        "route_id": route_id,
        "preference": preference,
        "language": language,
    }


def _detect_language(message):
    if re.search(r"[\u0600-\u06FF]", message):       # Arabic/Urdu script
        return "urdu"
    roman_urdu_words = (
        "kaise", "kese", "jana", "jaana", "batao", "kitna", "kitne", "sasti",
        "sasta", "kahan", "kahaan", "hai", "se", "tak", "chahiye", "kya",
    )
    words = set(re.findall(r"[a-z]+", message.lower()))
    return "roman_urdu" if words & set(roman_urdu_words) else "en"


# ---------------------------------------------------------------------------
# Fallback: keyword rules, used only when the LLM call fails.
# Keeps the demo alive if the API key, quota or network is down.
# ---------------------------------------------------------------------------

_FROM_TO = [
    re.compile(r"(?:from\s+)?(?P<a>.+?)\s+(?:se|to|se lekar)\s+(?P<b>.+)$",
               re.IGNORECASE),
]

# Words users add after a stop name that are not part of it.
_FILLER = {
    "tak", "jana", "jaana", "jaunga", "jaun", "kaise", "kese", "kaisay",
    "batao", "bata", "route", "ka", "ki", "ke", "hai", "he", "chahiye",
    "please", "plz", "sasti", "sasta", "wala", "chalo", "lie", "liye",
}


def _strip_filler(value):
    """Remove trailing filler words so 'Railway Station jana hai' -> 'Railway Station'."""
    if not value:
        return value
    words = value.strip(" ,?.").split()
    while words and words[-1].lower() in _FILLER:
        words.pop()
    return " ".join(words) or None


def _rule_based(message):
    text = message.strip()
    language = _detect_language(text)
    lower = text.lower()

    route_match = re.search(r"\b(FRT\d{2}|LMB-?L?\d)\b", text, re.IGNORECASE)
    preference = "cheapest" if re.search(r"sast|cheap", lower) else None

    if re.fullmatch(r"(hi|hello|salam|assalam[ou]? ?alaikum|hey)\W*", lower):
        intent = "greeting"
    elif route_match:
        intent = "route_info"
    elif re.search(r"fare|kiraya|kitne ka|cost|paisa|rupee|rs", lower):
        intent = "fare_info"
    elif re.search(r"time|timing|hours|kab|khul|band", lower):
        intent = "timing_info"
    else:
        intent = "faq"

    source = destination = None
    for pattern in _FROM_TO:
        match = pattern.match(text)
        if match:
            source = _strip_filler(match.group("a"))
            destination = _strip_filler(match.group("b"))
            if source and destination:
                intent = "plan_route"
                break

    return {
        "intent": intent,
        "source": source,
        "destination": destination,
        "stop": None,
        "route_id": route_match.group(0).upper() if route_match else None,
        "preference": preference,
        "language": language,
    }