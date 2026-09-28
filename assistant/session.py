"""
Short-term conversation memory.

This is what makes the assistant feel like an assistant instead of a
search box. Without it, "aur koi option hai?" means nothing.

Stored per session:
    history : last few turns (user + assistant text)
    slots   : last known source / destination / stop / route_id

In-memory only, so it resets when the server restarts. That is fine for
the FYP demo. TODO (Phase 9/12): move to MongoDB if chat history must
survive restarts.
"""

from collections import deque

MAX_TURNS = 6           # 3 user + 3 assistant messages kept for context
MAX_SESSIONS = 500      # simple guard against unbounded memory growth

_sessions = {}


def _blank():
    return {
        "history": deque(maxlen=MAX_TURNS),
        "slots": {"source": None, "destination": None,
                  "stop": None, "route_id": None},
    }


def get_session(session_id):
    if session_id not in _sessions:
        if len(_sessions) >= MAX_SESSIONS:
            _sessions.pop(next(iter(_sessions)))
        _sessions[session_id] = _blank()
    return _sessions[session_id]


def add_turn(session_id, role, text):
    get_session(session_id)["history"].append({"role": role, "content": text})


def history_as_text(session_id):
    """Compact transcript handed to the intent parser."""
    turns = get_session(session_id)["history"]
    if not turns:
        return "(no previous messages)"
    return "\n".join(f"{t['role']}: {t['content']}" for t in turns)


def update_slots(session_id, **values):
    slots = get_session(session_id)["slots"]
    for key, value in values.items():
        if value:
            slots[key] = value


def get_slots(session_id):
    return dict(get_session(session_id)["slots"])


def reset(session_id):
    _sessions.pop(session_id, None)