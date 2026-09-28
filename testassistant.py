"""
Manual test for the assistant pipeline.

Run:  python test_assistant.py
This calls the real LLM, so it needs GROQ_API_KEY in .env.

The last block tests conversation memory: the follow-up questions have no
source or destination in them, so they only work if session memory works.
"""

from assistant.pipeline import answer

SINGLE_TURN = [
    "hello",
    "what can you do?",
    "Kalma Chowk se Railway Station kaise jaun?",
    "bhatti chowk se r.a bazar sasti route batao",
    "R.A Bazar par kaunsi bus rukti hai?",
    "FRT09 ke stops batao",
    "Metrobus ka fare kitna hai?",
    "feeder routes ki timing kya hai?",
    "nowhere place se liberty",
    "who won the cricket match yesterday?",
]

FOLLOW_UP = [
    "Kalma Chowk se Chuburji jana hai",
    "aur koi option hai?",
    "iska fare kitna hai?",
]


def show(message, session_id):
    result = answer(message, session_id)
    print(f"\nUSER   : {message}")
    print(f"INTENT : {result['intent']['intent']}  "
          f"(lang={result['intent']['language']})")
    print(f"BOT    : {result['response']}")


if __name__ == "__main__":
    print("=" * 60)
    print("SINGLE-TURN TESTS")
    print("=" * 60)
    for index, message in enumerate(SINGLE_TURN):
        show(message, f"test-{index}")

    print("\n" + "=" * 60)
    print("CONVERSATION MEMORY TEST (same session)")
    print("=" * 60)
    for message in FOLLOW_UP:
        show(message, "memory-test")