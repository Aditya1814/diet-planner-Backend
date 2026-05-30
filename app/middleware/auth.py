"""JWT authentication middleware for FastAPI using Supabase JWKS."""

import httpx
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError, jwk
from jose.utils import base64url_decode
import json
from functools import lru_cache

from app.config import get_settings

security = HTTPBearer()

# Cache the JWKS keys to avoid fetching on every request
_jwks_cache = {"keys": None}


def _get_jwks_url() -> str:
    """Build the JWKS URL from the Supabase project URL."""
    settings = get_settings()
    # Remove trailing slash if present
    base_url = settings.supabase_url.rstrip("/")
    return f"{base_url}/auth/v1/.well-known/jwks.json"


def _fetch_jwks() -> list:
    """Fetch JWKS keys from Supabase. Cached after first call."""
    if _jwks_cache["keys"] is not None:
        return _jwks_cache["keys"]

    url = _get_jwks_url()
    try:
        response = httpx.get(url, timeout=10.0)
        response.raise_for_status()
        data = response.json()
        _jwks_cache["keys"] = data.get("keys", [])
        return _jwks_cache["keys"]
    except Exception:
        return []


def _get_signing_key(token: str) -> dict:
    """Get the appropriate signing key from JWKS based on the token's kid."""
    try:
        # Decode the token header without verification to get the kid
        unverified_header = jwt.get_unverified_header(token)
    except JWTError:
        raise HTTPException(
            status_code=401,
            detail="Invalid authentication credentials",
        )

    kid = unverified_header.get("kid")
    alg = unverified_header.get("alg", "ES256")

    jwks_keys = _fetch_jwks()

    for key in jwks_keys:
        if key.get("kid") == kid:
            return key

    # If no kid match, try the first key
    if jwks_keys:
        return jwks_keys[0]

    raise HTTPException(
        status_code=401,
        detail="Invalid authentication credentials",
    )


async def verify_jwt(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    """
    Verify the JWT token from the Authorization header against Supabase JWKS.

    Supports both ES256 (asymmetric, new Supabase default) and HS256 (legacy).
    Returns the decoded token payload containing user information.
    Raises HTTPException 401 if the token is invalid or expired.
    """
    settings = get_settings()
    token = credentials.credentials

    try:
        # Get the unverified header to determine the algorithm
        unverified_header = jwt.get_unverified_header(token)
        alg = unverified_header.get("alg", "HS256")

        if alg == "HS256":
            # Legacy: verify with the JWT secret directly
            payload = jwt.decode(
                token,
                settings.supabase_jwt_secret,
                algorithms=["HS256"],
                audience="authenticated",
            )
        else:
            # ES256 or other asymmetric: verify with JWKS public key
            signing_key = _get_signing_key(token)
            payload = jwt.decode(
                token,
                signing_key,
                algorithms=[alg],
                audience="authenticated",
            )

        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=401,
                detail="Invalid authentication credentials",
            )
        return payload
    except JWTError:
        raise HTTPException(
            status_code=401,
            detail="Invalid authentication credentials",
        )


async def get_current_user_id(
    payload: dict = Depends(verify_jwt),
) -> str:
    """Extract the current user ID from the verified JWT payload."""
    return payload["sub"]
