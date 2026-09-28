"""
Transit AI - Request and response models.

These classes tell FastAPI what data an endpoint accepts and what it
returns. FastAPI validates every incoming request against them, so
invalid data is rejected before it reaches our database code.
"""

from pydantic import BaseModel, EmailStr, Field


# ============================================================
# AUTHENTICATION
# ============================================================

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
    full_name: str = Field(min_length=2, max_length=100)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=72)


class UserResponse(BaseModel):
    user_id: str
    email: str
    full_name: str | None = None
    role: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


# ============================================================
# CHAT
# ============================================================

class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=1000)


class ChatResponse(BaseModel):
    response: str