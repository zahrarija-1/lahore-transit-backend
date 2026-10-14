"""
Transit AI - Authentication.

Three jobs:

1. Turn a password into a bcrypt hash, and check a password against
   a stored hash. The plain password is never stored anywhere.
2. Create and read JWT tokens, so a logged-in user does not have to
   send their password with every request.
3. Provide get_current_user(), which any endpoint can use to require
   a valid login.
"""

import sqlite3
import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from config import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    JWT_ALGORITHM,
    JWT_SECRET_KEY,
)
from supabase_client import supabase, supabase_admin
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
DB_PATH = "transit_ai.db"

# Tells FastAPI to read the "Authorization: Bearer <token>" header.
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

def get_connection():
    return sqlite3.connect(DB_PATH)


def now_iso():
    return datetime.now(timezone.utc).isoformat()


# ============================================================
# PASSWORD HASHING
# ============================================================

def hash_password(password):
    """Turn a plain password into a bcrypt hash."""

    hashed = bcrypt.hashpw(
        password.encode("utf-8"),
        bcrypt.gensalt()
    )

    return hashed.decode("utf-8")


def verify_password(password, password_hash):
    """Check a plain password against a stored hash."""

    try:
        return bcrypt.checkpw(
            password.encode("utf-8"),
            password_hash.encode("utf-8")
        )

    except (ValueError, TypeError):
        # Stored hash is corrupt or missing. Treat as a failed login
        # rather than crashing the request.
        return False


# ============================================================
# JWT TOKENS
# ============================================================

def create_access_token(user_id, email):
    """Create a signed token that proves who the user is."""

    expires_at = datetime.now(timezone.utc) + timedelta(
        minutes=ACCESS_TOKEN_EXPIRE_MINUTES
    )

    payload = {
        "sub": user_id,
        "email": email,
        "exp": expires_at
    }

    return jwt.encode(
        payload,
        JWT_SECRET_KEY,
        algorithm=JWT_ALGORITHM
    )


def decode_access_token(token):
    """Read a token. Raises HTTPException if it is invalid."""

    try:
        return jwt.decode(
            token,
            JWT_SECRET_KEY,
            algorithms=[JWT_ALGORITHM]
        )

    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"}
        )

    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token.",
            headers={"WWW-Authenticate": "Bearer"}
        )



# ============================================================
# USER DATABASE QUERIES - SUPABASE AUTH
# ============================================================

def _format_user(auth_user):
    if auth_user is None:
        return None

    metadata = auth_user.user_metadata or {}

    return {
        "user_id": str(auth_user.id),
        "email": auth_user.email,
        "full_name": metadata.get("full_name", ""),
        "role": metadata.get("role", "user"),
        "is_active": True,
        "created_at": str(auth_user.created_at or ""),
    }




def get_user_by_id(user_id):
    try:
        response = supabase_admin.auth.admin.get_user_by_id(str(user_id))

        if response.user is None:
            return None

        return _format_user(response.user)

    except Exception as exc:
        print(
            "SUPABASE USER LOOKUP ERROR:",
            type(exc).__name__,
            str(exc)
        )
        raise HTTPException(
            status_code=503,
            detail="Unable to verify user account."
        ) from exc

def get_user_by_email(email):
    # Password authentication is handled by Supabase Auth.
    # Do not retrieve password hashes through this function.
    return None

def create_user(email, password, full_name):
    try:
        response = supabase.auth.sign_up({
            "email": email,
            "password": password,
            "options": {
                "data": {
                    "full_name": full_name,
                    "role": "user"
                }
            }
        })

        if response.user is None:
            raise HTTPException(
                status_code=400,
                detail="Unable to create account."
            )


        return _format_user(response.user)

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail="Account registration failed. Check your email or try again."
        ) from exc


security = HTTPBearer()
# ============================================================
# LOGIN REQUIRED DEPENDENCY
# ============================================================

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Add this to any endpoint that should require a login:

        def my_endpoint(user: dict = Depends(get_current_user)):

    FastAPI then rejects the request with 401 unless a valid token
    is supplied.
    """

    payload = decode_access_token(credentials.credentials)

    user_id = payload.get("sub")

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token."
        )

    user = get_user_by_id(user_id)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="This user account no longer exists."
        )

    if not user["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account has been disabled."
        )

    return user


def require_admin(current_user: dict = Depends(get_current_user)):
    """Same as get_current_user, but also requires role = admin."""

    if current_user["role"] != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator access is required."
        )

    return current_user