"""Authentication routes for user registration, login, and logout."""

import re
from datetime import datetime, timedelta, timezone
from collections import defaultdict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.database import get_supabase_client

router = APIRouter(prefix="/api/auth", tags=["auth"])

# In-memory store for failed login attempts tracking
# Structure: {email: {"count": int, "locked_until": datetime | None, "last_attempt": datetime}}
_failed_attempts: dict[str, dict] = defaultdict(
    lambda: {"count": 0, "locked_until": None, "last_attempt": None}
)

MAX_FAILED_ATTEMPTS = 5
LOCKOUT_DURATION_MINUTES = 15

# Email validation regex: local part + @ + domain
EMAIL_REGEX = re.compile(
    r"^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$"
)


class RegisterRequest(BaseModel):
    """Request body for user registration."""

    email: str = Field(..., description="User email address")
    password: str = Field(..., description="User password")


class LoginRequest(BaseModel):
    """Request body for user login."""

    email: str = Field(..., description="User email address")
    password: str = Field(..., description="User password")


class LogoutRequest(BaseModel):
    """Request body for user logout."""

    access_token: str = Field(..., description="Current access token to invalidate")


def validate_email(email: str) -> bool:
    """Validate email format: must have local part, @, and domain."""
    if not email or not EMAIL_REGEX.match(email):
        return False
    # Ensure domain has at least one dot for a valid TLD
    domain = email.split("@")[1]
    if "." not in domain:
        return False
    return True


def validate_password(password: str) -> bool:
    """Validate password length: must be between 8 and 128 characters."""
    return 8 <= len(password) <= 128


def _is_account_locked(email: str) -> bool:
    """Check if an account is currently locked due to failed attempts."""
    record = _failed_attempts[email]
    if record["locked_until"] is None:
        return False
    now = datetime.now(timezone.utc)
    if now < record["locked_until"]:
        return True
    # Lockout expired, reset
    _failed_attempts[email] = {"count": 0, "locked_until": None, "last_attempt": None}
    return False


def _record_failed_attempt(email: str) -> None:
    """Record a failed login attempt and lock account if threshold reached."""
    record = _failed_attempts[email]
    record["count"] += 1
    record["last_attempt"] = datetime.now(timezone.utc)
    if record["count"] >= MAX_FAILED_ATTEMPTS:
        record["locked_until"] = datetime.now(timezone.utc) + timedelta(
            minutes=LOCKOUT_DURATION_MINUTES
        )


def _reset_failed_attempts(email: str) -> None:
    """Reset failed attempt counter on successful login."""
    _failed_attempts[email] = {"count": 0, "locked_until": None, "last_attempt": None}


@router.post("/register", status_code=201)
async def register(request: RegisterRequest):
    """
    Register a new user account.

    Validates email format and password length requirements before
    creating the account via Supabase Auth.
    """
    # Validate email format
    if not validate_email(request.email):
        raise HTTPException(
            status_code=422,
            detail="Invalid email format. Email must contain a local part, '@' symbol, and a valid domain.",
        )

    # Validate password length
    if not validate_password(request.password):
        raise HTTPException(
            status_code=422,
            detail="Password must be between 8 and 128 characters long.",
        )

    supabase = get_supabase_client()

    try:
        response = supabase.auth.sign_up(
            {"email": request.email, "password": request.password}
        )

        # Supabase returns a user even if email already exists (with identities=[])
        if response.user and not response.user.identities:
            raise HTTPException(
                status_code=409,
                detail="An account with this email already exists.",
            )

        return {"message": "Registration successful. Please log in."}
    except HTTPException:
        raise
    except Exception as e:
        error_message = str(e).lower()
        if "already registered" in error_message or "already exists" in error_message:
            raise HTTPException(
                status_code=409,
                detail="An account with this email already exists.",
            )
        raise HTTPException(
            status_code=500,
            detail="Registration failed. Please try again.",
        )


@router.post("/login")
async def login(request: LoginRequest):
    """
    Authenticate a user and return session tokens.

    Implements account lockout after 5 consecutive failed attempts
    for 15 minutes. Returns generic error messages to avoid revealing
    which field is incorrect.
    """
    email = request.email.lower().strip()

    # Check if account is locked
    if _is_account_locked(email):
        raise HTTPException(
            status_code=429,
            detail="Account temporarily locked due to too many failed attempts. Please try again in 15 minutes.",
        )

    supabase = get_supabase_client()

    try:
        response = supabase.auth.sign_in_with_password(
            {"email": request.email, "password": request.password}
        )

        # Successful login - reset failed attempts
        _reset_failed_attempts(email)

        return {
            "access_token": response.session.access_token,
            "refresh_token": response.session.refresh_token,
            "token_type": "bearer",
            "expires_in": response.session.expires_in,
            "user": {
                "id": response.user.id,
                "email": response.user.email,
            },
        }
    except Exception as e:
        error_message = str(e).lower()
        if "invalid" in error_message or "credentials" in error_message or "not found" in error_message:
            # Record failed attempt
            _record_failed_attempt(email)

            # Check if this attempt triggered a lockout
            if _is_account_locked(email):
                raise HTTPException(
                    status_code=429,
                    detail="Account temporarily locked due to too many failed attempts. Please try again in 15 minutes.",
                )

            # Generic error message - don't reveal which field is wrong
            raise HTTPException(
                status_code=401,
                detail="Invalid email or password.",
            )

        raise HTTPException(
            status_code=500,
            detail="Authentication failed. Please try again.",
        )


@router.post("/logout")
async def logout(request: LogoutRequest):
    """
    Terminate the user's session.

    Invalidates the provided access token via Supabase Auth.
    """
    supabase = get_supabase_client()

    try:
        # Use admin client to sign out the user by their token
        supabase.auth.admin.sign_out(request.access_token)
    except Exception:
        # Even if sign-out fails server-side, we consider it successful
        # The token will expire naturally
        pass

    return {"message": "Logged out successfully."}
