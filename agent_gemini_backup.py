from google import genai
from google.genai import types

from config import GEMINI_API_KEY, MODEL_NAME
from db_tools import (
    route_information,
    get_route_stops,
    get_stop_routes,
    fare_calculator,
    service_information,
    route_search
)
from rag import search_transit_knowledge


# -----------------------------------
# Gemini Client
# -----------------------------------

client = genai.Client(api_key=GEMINI_API_KEY)


# -----------------------------------
# Tool Declarations
# -----------------------------------

route_information_tool = {
    "name": "route_information",
    "description": "Get complete information about a Lahore public transport route.",
    "parameters": {
        "type": "object",
        "properties": {
            "route_id": {
                "type": "string",
                "description": "Route ID such as FRT09."
            }
        },
        "required": ["route_id"]
    }
}


get_route_stops_tool = {
    "name": "get_route_stops",
    "description": "Get all stops of a Lahore public transport route in order.",
    "parameters": {
        "type": "object",
        "properties": {
            "route_id": {
                "type": "string",
                "description": "Route ID such as FRT09."
            }
        },
        "required": ["route_id"]
    }
}


get_stop_routes_tool = {
    "name": "get_stop_routes",
    "description": "Find public transport routes serving a particular Lahore stop.",
    "parameters": {
        "type": "object",
        "properties": {
            "stop_name": {
                "type": "string",
                "description": "Name of the transit stop."
            }
        },
        "required": ["stop_name"]
    }
}


fare_calculator_tool = {
    "name": "fare_calculator",
    "description": "Find Lahore public transport fare information.",
    "parameters": {
        "type": "object",
        "properties": {
            "service_type": {
                "type": "string",
                "description": "Service such as Metrobus or Feeder."
            },
            "journey_type": {
                "type": "string",
                "description": "Journey or fare rule if specified."
            }
        }
    }
}


service_information_tool = {
    "name": "service_information",
    "description": "Get operating hours and service information.",
    "parameters": {
        "type": "object",
        "properties": {
            "service_query": {
                "type": "string",
                "description": "Service name such as Metrobus."
            }
        },
        "required": ["service_query"]
    }
}


route_search_tool = {
    "name": "route_search",
    "description": "Find direct Lahore public transport routes between two stops.",
    "parameters": {
        "type": "object",
        "properties": {
            "origin": {
                "type": "string",
                "description": "Starting transit stop."
            },
            "destination": {
                "type": "string",
                "description": "Destination transit stop."
            }
        },
        "required": ["origin", "destination"]
    }
}


TOOL_DECLARATIONS = types.Tool(
    function_declarations=[
        types.FunctionDeclaration(**route_information_tool),
        types.FunctionDeclaration(**get_route_stops_tool),
        types.FunctionDeclaration(**get_stop_routes_tool),
        types.FunctionDeclaration(**fare_calculator_tool),
        types.FunctionDeclaration(**service_information_tool),
        types.FunctionDeclaration(**route_search_tool)
    ]
)


# -----------------------------------
# Available Tools
# -----------------------------------

AVAILABLE_TOOLS = {
    "route_information": route_information,
    "get_route_stops": get_route_stops,
    "get_stop_routes": get_stop_routes,
    "fare_calculator": fare_calculator,
    "service_information": service_information,
    "route_search": route_search
}


# -----------------------------------
# Transit AI System Prompt
# -----------------------------------

TRANSIT_AGENT_PROMPT = """
You are Transit AI, an intelligent Lahore public transportation assistant.

Your purpose is to help users understand and navigate Lahore public transportation.

You have access to:

1. A RAG knowledge base containing verified Lahore transit information.
2. Structured database tools for routes, stops, fares and services.

IMPORTANT RULES:

1. Use tools whenever the user asks for specific:
   - route information
   - route stops
   - stop information
   - fares
   - operating hours
   - journey/route information

2. NEVER invent a route, stop, fare, operating time or transit fact.

3. For origin-to-destination questions ALWAYS use route_search.

4. Only recommend routes returned by route_search.

5. If no direct route is found, clearly say that no direct route
   was found.

6. Do NOT invent transfer routes.

7. Do NOT claim live GPS, live traffic, live crowd levels,
   or ETA because these features are not currently available.

8. Understand:
   - English
   - Roman Urdu
   - Urdu
   - mixed English/Roman Urdu

9. For general transit questions, use the RAG knowledge base.

10. Keep responses concise, natural and useful.

11. Mention route IDs and important journey details when available.

12. Transit AI is specifically for Lahore public transportation.
"""


# -----------------------------------
# JSON Safety
# -----------------------------------

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


# -----------------------------------
# RAG Context
# -----------------------------------

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
Relevance: {result['score']:.4f}

{result['text']}
"""
        )

    return "\n".join(context_parts)


# -----------------------------------
# Transit AI Agent
# -----------------------------------

def transit_agent(question):

    rag_context = get_rag_context(question)

    prompt = f"""
{TRANSIT_AGENT_PROMPT}

RELEVANT TRANSIT KNOWLEDGE:

--------------------------------
{rag_context}
--------------------------------

USER QUESTION:

{question}

Answer the user using the knowledge above and the available tools.
"""

    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=prompt,
        config=types.GenerateContentConfig(
            tools=[TOOL_DECLARATIONS]
        )
    )

    # --------------------------------
    # Tool call
    # --------------------------------

    if response.function_calls:

        tool_call = response.function_calls[0]

        tool_name = tool_call.name
        tool_args = dict(tool_call.args)

        print("\n🔧 Tool selected:", tool_name)
        print("📥 Arguments:", tool_args)

        if tool_name not in AVAILABLE_TOOLS:

            return "Sorry, I don't have the required transit tool."

        function = AVAILABLE_TOOLS[tool_name]

        tool_result = function(**tool_args)

        tool_result = make_json_safe(tool_result)

        print("📤 Tool result:")
        print(tool_result)

        function_response_part = types.Part.from_function_response(
            name=tool_name,
            response={
                "result": tool_result
            }
        )

        final_response = client.models.generate_content(

            model=MODEL_NAME,

            contents=[
                prompt,
                response.candidates[0].content,

                types.Content(
                    role="user",
                    parts=[
                        function_response_part
                    ]
                )
            ],

            config=types.GenerateContentConfig(
                tools=[TOOL_DECLARATIONS]
            )
        )

        return final_response.text

    # --------------------------------
    # Normal RAG response
    # --------------------------------

    return response.text