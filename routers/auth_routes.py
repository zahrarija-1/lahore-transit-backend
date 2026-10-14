"""
Transit AI - Authentication endpoints.

POST /auth/register   create an account
POST /auth/login      get a token
GET  /auth/me         who am I (token required)
"""

from fastapi import APIRouter, Depends, HTTPException, status

from auth import (
    create_access_token,
    create_user,
    get_current_user,
    get_user_by_email,
    verify_password,
)
from schemas import (
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"]
)


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED
)
def register(request: RegisterRequest):
    """Create a new account and return a token straight away."""

    email = request.email.lower().strip()
    full_name = request.full_name.strip()

    user = create_user(
        email=email,
        password=request.password,
        full_name=full_name
    )

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists."
        )

    token = create_access_token(
        user["user_id"],
        user["email"]
    )

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": user
    }



@router.post("/login", response_model=TokenResponse)
def login(request: LoginRequest):
    email = request.email.lower().strip()

    try:
        from supabase_client import supabase

        response = supabase.auth.sign_in_with_password({
            "email": email,
            "password": request.password
        })

        if response.user is None or response.session is None:
            raise HTTPException(
                status_code=401,
                detail="Incorrect email or password."
            )

        metadata = response.user.user_metadata or {}

        user = {
            "user_id": str(response.user.id),
            "email": response.user.email,
            "full_name": metadata.get("full_name", ""),
            "role": "user"
        }

        token = create_access_token(
            user["user_id"],
            user["email"]
        )

        return {
            "access_token": token,
            "token_type": "bearer",
            "user": user
        }

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=401,
            detail="Incorrect email or password."
        ) from exc



@router.get("/me", response_model=UserResponse)
def me(current_user: dict = Depends(get_current_user)):
    """Return the logged-in user's profile."""

    return current_user