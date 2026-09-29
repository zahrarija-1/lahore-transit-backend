```python
"""
Short-term conversation memory.

This stores a small amount of conversation context for each session.

Stored per session:
    history : last few turns (user + assistant text)
    slots   : last known source / destination / stop / route_id

In-memory only, so it resets when the server restarts.
That is fine for the FYP demo.

TODO:
    Move conversation history to Supabase/MongoDB later if it
    needs to survive server restarts.
"""

from collections import deque


MAX_TURNS = 6       # 3 user + 3 assistant messages kept for context
MAX_SESSIONS = 500  # Guard against unbounded memory growth

_sessions = {}


def _blank():
    """Create a fresh session."""
    return {
        "history": deque(maxlen=MAX_TURNS),
        "slots": {
            "source": None,
            "destination": None,
            "stop": None,
            "route_id": None,
        },
    }


def get_session(session_id):
    """
    Get an existing session or create a new one.
    """
    if not session_id:
        session_id = "default"

    if session_id not in _sessions:
        if len(_sessions) >= MAX_SESSIONS:
            # Remove the oldest inserted session.
            _sessions.pop(next(iter(_sessions)))

        _sessions[session_id] = _blank()

    return _sessions[session_id]


def add_turn(session_id, role, text):
    """
    Add one user/assistant turn to the conversation history.
    """
    session = get_session(session_id)

    session["history"].append(
        {
            "role": role,
            "content": text,
        }
    )


def add_message(session_id, role, text):
    """
    Compatibility wrapper for the chat endpoint.

    main.py uses session.add_message(), while the original
    session module used add_turn(). Both now work.
    """
    add_turn(session_id, role, text)


def history_as_text(session_id):
    """
    Return a compact transcript for the intent parser / assistant.
    """
    turns = get_session(session_id)["history"]

    if not turns:
        return "(no previous messages)"

    return "\n".join(
        f"{turn['role']}: {turn['content']}"
        for turn in turns
    )


def update_slots(session_id, **values):
    """
    Update known conversation slots.

    Empty/None values are ignored so that an incomplete
    request does not overwrite information we already know.
    """
    slots = get_session(session_id)["slots"]

    for key, value in values.items():
        if key in slots and value is not None and value != "":
            slots[key] = value


def get_slots(session_id):
    """
    Return a copy of the current conversation slots.
    """
    return dict(get_session(session_id)["slots"])


def reset(session_id):
    """
    Completely remove a session and its conversation context.
    """
    if session_id:
        _sessions.pop(session_id, None)
```
