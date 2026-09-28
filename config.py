import os
from dotenv import load_dotenv

load_dotenv()

# ============================================================
# GROQ
# ============================================================

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not GROQ_API_KEY:
    raise ValueError(
        "GROQ_API_KEY was not found. "
        "Please add it to the .env file."
    )

MODEL_NAME = "openai/gpt-oss-120b"


# ============================================================
# SUPABASE
# ============================================================

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

if not SUPABASE_URL:
    raise ValueError(
        "SUPABASE_URL was not found. "
        "Please add it to the .env file."
    )

if not SUPABASE_SERVICE_ROLE_KEY:
    raise ValueError(
        "SUPABASE_SERVICE_ROLE_KEY was not found. "
        "Please add it to the .env file."
    )


# ============================================================
# AUTHENTICATION
# ============================================================

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")

if not JWT_SECRET_KEY:
    raise ValueError(
        "JWT_SECRET_KEY was not found. "
        "Please add it to the .env file."
    )

JWT_ALGORITHM = "HS256"

# How long a login lasts before the user must sign in again.
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours