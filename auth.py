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
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from config import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    JWT_ALGORITHM,
    JWT_SECRET_KEY,
)

DB_PATH = "transit_ai.db"

# Tells FastAPI to read the "Authorization: Bearer <token>" header.
security = HTTPBearer()


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
# USER DATABASE QUERIES
# ============================================================

def get_user_by_email(email):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            user_id,
            email,
            password_hash,
            full_name,
            role,
            is_active
        FROM users
        WHERE email = ?
    """, (email,))

    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    return {
        "user_id": row[0],
        "email": row[1],
        "password_hash": row[2],
        "full_name": row[3],
        "role": row[4],
        "is_active": bool(row[5])
    }


def get_user_by_id(user_id):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            user_id,
            email,
            full_name,
            role,
            is_active,
            created_at
        FROM users
        WHERE user_id = ?
    """, (user_id,))

    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    return {
        "user_id": row[0],
        "email": row[1],
        "full_name": row[2],
        "role": row[3],
        "is_active": bool(row[4]),
        "created_at": row[5]
    }


def create_user(email, password, full_name):
    """
    Insert a new user.

    Returns None if the email is already registered. The UNIQUE
    constraint on the email column is what actually prevents the
    duplicate, so two simultaneous signups cannot both succeed.
    """

    user_id = str(uuid.uuid4())
    timestamp = now_iso()

    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            INSERT INTO users (
                user_id,
                email,
                password_hash,
                full_name,
                role,
                is_active,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            user_id,
            email,
            hash_password(password),
            full_name,
            "user",
            1,
            timestamp,
            timestamp
        ))

        conn.commit()

    except sqlite3.IntegrityError:
        conn.close()
        return None

    finally:
        if conn:
            conn.close()

    return {
        "user_id": user_id,
        "email": email,
        "full_name": full_name,
        "role": "user"
    }


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