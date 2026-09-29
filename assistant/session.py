from collections import deque

MAX_TURNS = 6
MAX_SESSIONS = 500

_sessions = {}


def _blank():
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
    if not session_id:
        session_id = "default"

    if session_id not in _sessions:
        if len(_sessions) >= MAX_SESSIONS:
            oldest_session = next(iter(_sessions))
            _sessions.pop(oldest_session)

        _sessions[session_id] = _blank()

    return _sessions[session_id]


def add_turn(session_id, role, text):
    get_session(session_id)["history"].append({
        "role": role,
        "content": text,
    })


def add_message(session_id, role, text):
    add_turn(session_id, role, text)


def history_as_text(session_id):
    turns = get_session(session_id)["history"]

    if not turns:
        return "(no previous messages)"

    return "\n".join(
        f"{turn['role']}: {turn['content']}"
        for turn in turns
    )


def update_slots(session_id, **values):
    slots = get_session(session_id)["slots"]

    for key, value in values.items():
        if key in slots and value is not None and value != "":
            slots[key] = value


def get_slots(session_id):
    return dict(get_session(session_id)["slots"])


def reset(session_id):
    if session_id:
        _sessions.pop(session_id, None)