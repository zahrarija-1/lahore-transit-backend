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
    """Check the password and return a token."""

    email = request.email.lower().strip()

    user = get_user_by_email(email)

    # The same message is returned whether the email is unknown or
    # the password is wrong. Otherwise anyone could use this endpoint
    # to discover which email addresses are registered.
    if not user or not verify_password(
        request.password,
        user["password_hash"]
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password."
        )

    if not user["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account has been disabled."
        )

    token = create_access_token(
        user["user_id"],
        user["email"]
    )

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "user_id": user["user_id"],
            "email": user["email"],
            "full_name": user["full_name"],
            "role": user["role"]
        }
    }


@router.get("/me", response_model=UserResponse)
def me(current_user: dict = Depends(get_current_user)):
    """Return the logged-in user's profile."""

    return current_user