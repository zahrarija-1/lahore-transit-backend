from groq import Groq
from config import GROQ_API_KEY, MODEL_NAME

client = Groq(api_key=GROQ_API_KEY)

response = client.chat.completions.create(
    model=MODEL_NAME,
    messages=[
        {
            "role": "user",
            "content": "Say hello to Transit AI in one sentence."
        }
    ]
)

print(response.choices[0].message.content)