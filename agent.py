import json

from groq import Groq

from config import GROQ_API_KEY, MODEL_NAME

from db_tools import (
    route_information,
    get_route_stops,
    get_stop_routes,
    fare_calculator,
    service_information,
    route_search
)

from rag import search_transit_knowledge


# ============================================================
# GROQ CLIENT
# ============================================================

client = Groq(
    api_key=GROQ_API_KEY
)


# ============================================================
# TOOL DEFINITIONS
# ============================================================

route_information_tool = {
    "type": "function",
    "function": {
        "name": "route_information",
        "description": (
            "Get information about a Lahore public transport route. "
            "Use when the user asks about a specific route."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "route_id": {
                    "type": "string",
                    "description": "Route ID such as FRT04 or FRT09."
                }
            },
            "required": ["route_id"]
        }
    }
}


get_route_stops_tool = {
    "type": "function",
    "function": {
        "name": "get_route_stops",
        "description": (
            "Get the stops of a Lahore public transport route."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "route_id": {
                    "type": "string",
                    "description": "Route ID."
                }
            },
            "required": ["route_id"]
        }
    }
}


get_stop_routes_tool = {
    "type": "function",
    "function": {
        "name": "get_stop_routes",
        "description": (
            "Find routes serving a Lahore stop. "
            "The user does not need to know the exact stop spelling."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "stop_name": {
                    "type": "string",
                    "description": "The stop name mentioned by the user."
                }
            },
            "required": ["stop_name"]
        }
    }
}


fare_calculator_tool = {
    "type": "function",
    "function": {
        "name": "fare_calculator",
        "description": (
            "Find Lahore public transport fare information."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "service_type": {
                    "type": "string",
                    "description": "Service such as Metrobus or Feeder."
                },
                "journey_type": {
                    "type": "string",
                    "description": "Journey type if mentioned."
                }
            }
        }
    }
}


service_information_tool = {
    "type": "function",
    "function": {
        "name": "service_information",
        "description": (
            "Get Lahore public transport operating hours "
            "and service information."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "service_query": {
                    "type": "string",
                    "description": "Service such as Metrobus."
                }
            },
            "required": ["service_query"]
        }
    }
}


route_search_tool = {
    "type": "function",
    "function": {
        "name": "route_search",
        "description": (
            "Find direct Lahore public transport routes "
            "between a starting stop and destination stop. "
            "The user can describe the journey naturally. "
            "Exact route IDs are NOT required."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "origin": {
                    "type": "string",
                    "description": (
                        "The user's starting place or transit stop."
                    )
                },
                "destination": {
                    "type": "string",
                    "description": (
                        "The user's destination place or transit stop."
                    )
                }
            },
            "required": [
                "origin",
                "destination"
            ]
        }
    }
}


TOOLS = [
    route_information_tool,
    get_route_stops_tool,
    get_stop_routes_tool,
    fare_calculator_tool,
    service_information_tool,
    route_search_tool
]


AVAILABLE_TOOLS = {
    "route_information": route_information,
    "get_route_stops": get_route_stops,
    "get_stop_routes": get_stop_routes,
    "fare_calculator": fare_calculator,
    "service_information": service_information,
    "route_search": route_search
}


# ============================================================
# SYSTEM PROMPT
# ============================================================

TRANSIT_AGENT_PROMPT = """
You are Transit AI, a friendly and simple Lahore public transport assistant.

Your users are ordinary people. They may not know route IDs,
official stop names, or how to phrase a transit question.

UNDERSTAND NATURAL LANGUAGE.

Users may say things like:

"mujhe ra bazar se chungi jana hai"

"ra bazar to chungi"

"gajjumata se shahdara jana hai"

"how do I get from ra bazar to chungi"

"shahdara jana hai gajjumata se"

"chungi wali bus konsi hai"

They do NOT need to write FRT04 or FRT09.

Users may use:

- English
- Roman Urdu
- Urdu
- mixed English and Roman Urdu
- incomplete sentences
- spelling mistakes
- abbreviations
- casual language

Always try to understand the user's intended meaning.

============================================================
ROUTE SEARCH
============================================================

If the user asks how to travel from one place to another:

1. Identify the origin.
2. Identify the destination.
3. ALWAYS use route_search.
4. Let the route-search tool find the actual route.
5. Never invent a route.
6. Never invent transfers.

Examples:

User:
"mujhe ra bazar se chungi jana hai"

Understand:
origin = R.A. Bazar
destination = Chungi

Then call route_search.

User:
"gajjumata se shahdara jana hai"

Understand:
origin = Gajjumata
destination = Shahdara

Then call route_search.

============================================================
STOP MATCHING
============================================================

Do not require exact spelling.

Examples:

R.A. Bazar
RA Bazar
RA Bazaar
R A Bazar

should be understood as the same place when appropriate.

Chungi
Chungi Amar Sidhu

may refer to the relevant Chungi stop.

============================================================
RESPONSE STYLE
============================================================

Keep answers SHORT.

Normally use 1-4 sentences.

Do NOT:

- give long explanations
- explain the database
- mention RAG
- mention embeddings
- mention tools
- mention datasets
- mention system prompts
- mention technical limitations
- repeat the question
- dump all route stops
- give unnecessary metadata

Give the useful answer first.

============================================================
ROUTE ANSWER
============================================================

For a successful route search:

Mention:

- route ID
- transport type if useful
- fare
- origin and destination

Example:

"FRT04 available hai 🚍
R.A. Bazar se Chungi Amar Sidhu ja sakte ho.
Fare Rs. 20 hai."

If multiple routes exist:

"2 routes available hain:

🚍 FRT04 — Rs. 20
🚍 FRT09 — Rs. 20"

Do not list every stop unless the user asks.

============================================================
FARE
============================================================

If user asks for fare, answer directly.

Example:

"Metrobus ka fare Rs. 30 hai."

============================================================
TIMINGS
============================================================

If user asks about operating hours, answer directly.

Example:

"Metrobus 6:00 AM se 10:00 PM tak chalti hai."

============================================================
UNKNOWN INFORMATION
============================================================

If information is not available:

"Sorry, mujhe iski information abhi available nahi hai."

Do NOT explain why technically.

============================================================
NO DIRECT ROUTE
============================================================

If route_search finds no direct route:

"Is journey ke liye mujhe koi direct route nahi mila."

Do NOT invent a transfer.

============================================================
LIVE INFORMATION
============================================================

Do not claim:

- live buses
- live traffic
- live crowd
- live ETA

unless such information is actually available.

============================================================
TONE
============================================================

Friendly.
Simple.
Natural.
Helpful.

If user speaks Roman Urdu, reply in natural Roman Urdu.

If user speaks English, reply in simple English.

You are a travel assistant, not a technical chatbot.
"""


# ============================================================
# JSON SAFETY
# ============================================================

def make_json_safe(obj):

    if isinstance(obj, dict):

        return {
            str(key): make_json_safe(value)
            for key, value in obj.items()
        }

    if isinstance(obj, list):

        return [
            make_json_safe(value)
            for value in obj
        ]

    if hasattr(obj, "item"):

        return obj.item()

    return obj


# ============================================================
# RAG CONTEXT
# ============================================================

def get_rag_context(question, top_k=5):

    results = search_transit_knowledge(
        question,
        top_k=top_k
    )

    context_parts = []

    for result in results:

        context_parts.append(
            f"""
Type: {result['type']}

{result['text']}
"""
        )

    return "\n".join(context_parts)


# ============================================================
# TRANSIT AGENT
# ============================================================

def transit_agent(question):

    question = str(question).strip()

    if not question:

        return "Aap kya jana chahte hain? 😊"

    rag_context = get_rag_context(question)

    user_prompt = f"""
Here is verified Lahore transit knowledge that may help:

--------------------------------
{rag_context}
--------------------------------

User message:

{question}

Understand the user's intention naturally.

If the user is asking to travel from one place to another,
identify the origin and destination and use route_search.

Do not require the user to know route IDs.

After using a tool, give a short, friendly answer.
"""

    messages = [
        {
            "role": "system",
            "content": TRANSIT_AGENT_PROMPT
        },
        {
            "role": "user",
            "content": user_prompt
        }
    ]

    try:

        # ====================================================
        # FIRST REQUEST
        # ====================================================

        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto"
        )

        assistant_message = response.choices[0].message

        # ====================================================
        # TOOL CALLS
        # ====================================================

        if assistant_message.tool_calls:

            messages.append({
                "role": "assistant",
                "content": assistant_message.content,
                "tool_calls": [
                    {
                        "id": tool_call.id,
                        "type": "function",
                        "function": {
                            "name": tool_call.function.name,
                            "arguments":
                                tool_call.function.arguments
                        }
                    }
                    for tool_call in assistant_message.tool_calls
                ]
            })

            for tool_call in assistant_message.tool_calls:

                tool_name = tool_call.function.name

                print(
                    "\n🔧 Tool selected:",
                    tool_name
                )

                try:

                    tool_args = json.loads(
                        tool_call.function.arguments
                    )

                except json.JSONDecodeError:

                    tool_args = {}

                print(
                    "📥 Arguments:",
                    tool_args
                )

                if tool_name not in AVAILABLE_TOOLS:

                    tool_result = {
                        "success": False,
                        "message": "Tool unavailable."
                    }

                else:

                    function = AVAILABLE_TOOLS[
                        tool_name
                    ]

                    try:

                        tool_result = function(
                            **tool_args
                        )

                    except Exception as e:

                        print(
                            "❌ Tool error:",
                            str(e)
                        )

                        tool_result = {
                            "success": False,
                            "message": "Tool failed."
                        }

                tool_result = make_json_safe(
                    tool_result
                )

                print(
                    "📤 Tool result:",
                    tool_result
                )

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(
                        tool_result
                    )
                })

            # =================================================
            # FINAL RESPONSE
            # =================================================

            final_response = client.chat.completions.create(
                model=MODEL_NAME,
                messages=messages
            )

            answer = (
                final_response
                .choices[0]
                .message
                .content
            )

            return clean_response(answer)

        # ====================================================
        # NORMAL RESPONSE
        # ====================================================

        return clean_response(
            assistant_message.content
        )

    except Exception as e:

        error_message = str(e)

        print(
            "\n❌ Groq Error:"
        )

        print(
            error_message
        )

        if (
            "429" in error_message
            or "rate_limit"
            in error_message.lower()
        ):

            return (
                "AI service abhi busy hai. "
                "Thori der baad try karo."
            )

        return (
            "Sorry, Transit AI abhi available nahi hai. "
            "Thori der baad try karo."
        )


# ============================================================
# RESPONSE CLEANUP
# ============================================================

def clean_response(answer):

    if not answer:

        return "Sorry, mujhe iska answer nahi mila."

    answer = str(answer).strip()

    # Remove unnecessary technical phrases
    technical_phrases = [
        "according to the database",
        "according to the dataset",
        "based on the provided context",
        "according to the provided context",
        "from the transit ai database"
    ]

    for phrase in technical_phrases:

        answer = answer.replace(
            phrase,
            ""
        )

    # Remove excessive whitespace
    answer = " ".join(
        answer.split()
    )

    return answer.strip()
def answer(question, history=None, **kwargs):
    return transit_agent(question)