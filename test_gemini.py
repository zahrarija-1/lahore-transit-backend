from google import genai
from config import GEMINI_API_KEY, MODEL_NAME

client = genai.Client(
    api_key=GEMINI_API_KEY
)

response = client.models.generate_content(
    model=MODEL_NAME,
    contents="Say hello from Transit AI in one sentence."
)

print("\nGemini response:")
print(response.text)