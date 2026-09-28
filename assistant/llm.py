"""
Single place where the LLM is called.

Everything else in the assistant imports from here, so switching provider
or model later means editing one file.

The LLM is used for exactly two things:
    1. understanding the user's sentence  (intent_parser.py)
    2. phrasing the final reply           (response_builder.py)

It never sees the database and never calculates anything.
"""

import json
import re

from groq import Groq

from config import GROQ_API_KEY, MODEL_NAME

_client = Groq(api_key=GROQ_API_KEY)


class LLMUnavailable(Exception):
    """Raised when the model cannot be reached, so callers can fall back."""


def complete(system_prompt, user_prompt, temperature=0.2, max_tokens=500):
    """Send one prompt, get plain text back."""
    try:
        response = _client.chat.completions.create(
            model=MODEL_NAME,
            temperature=temperature,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        return (response.choices[0].message.content or "").strip()
    except Exception as error:                      # network, quota, auth
        raise LLMUnavailable(str(error)) from error


def complete_json(system_prompt, user_prompt, temperature=0.0):
    """
    Same as complete(), but insists on a JSON object.

    Models often wrap JSON in ```json fences or add a sentence before it,
    so the first {...} block is extracted before parsing.
    """
    raw = complete(system_prompt, user_prompt, temperature=temperature,
                   max_tokens=300)
    raw = re.sub(r"^```(?:json)?|```$", "", raw.strip(),
                 flags=re.MULTILINE).strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not match:
            raise LLMUnavailable(f"Model did not return JSON: {raw[:200]}")
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError as error:
            raise LLMUnavailable(f"Invalid JSON from model: {raw[:200]}") from error