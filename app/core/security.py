"""
API key authentication for write operations.

Strategy:
    - READ endpoints (GET) are PUBLIC — anyone can query assets.
    - WRITE endpoints (POST, PUT, PATCH, DELETE) require a valid API key.

How it works:
    The client sends the API key in the `X-API-Key` HTTP header.
    This module provides a FastAPI dependency (`verify_api_key`) that
    checks that header against the key stored in settings.

    Usage in routers:
        @router.post("", dependencies=[Depends(verify_api_key)])
        async def create_something(...):
            ...

    The `dependencies=[...]` parameter on the route decorator means
    FastAPI will run `verify_api_key` BEFORE the route handler. If the
    key is missing or wrong, the request is rejected before the handler
    even executes.

Security note:
    We use `hmac.compare_digest()` instead of `==` for the key comparison.
    Why? A simple `==` comparison short-circuits on the first mismatched
    character. An attacker could measure response times to guess the key
    one character at a time (a "timing attack"). `compare_digest()` always
    takes the same amount of time regardless of where the mismatch is.
"""

import hmac
from typing import Optional

from fastapi import Header, HTTPException, status

from app.config import settings


async def verify_api_key(
    x_api_key: Optional[str] = Header(
        default=None,
        description="API key for authenticating write operations.",
    ),
) -> None:
    """
    FastAPI dependency that validates the X-API-Key header.

    Three possible outcomes:
        1. Header missing   → 401 Unauthorized
        2. Header present but wrong key → 403 Forbidden
        3. Header present and correct   → request proceeds

    Why 401 vs 403?
        - 401 Unauthorized: "I don't know who you are" (no credentials)
        - 403 Forbidden:    "I know who you are, but you're not allowed"
          (wrong credentials)

    This distinction helps API consumers debug authentication issues:
        - Getting 401? You forgot to include the X-API-Key header.
        - Getting 403? Your key is wrong.

    Parameters:
        x_api_key: The value of the X-API-Key header. FastAPI's `Header()`
                   function automatically reads this from the request headers.
                   The parameter name `x_api_key` maps to the header `X-API-Key`
                   (FastAPI converts underscores to hyphens automatically).
    """
    # Case 1: No API key provided at all
    if x_api_key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=(
                "Missing API key. Include the 'X-API-Key' header "
                "in your request to access write operations."
            ),
        )

    # Case 2: API key provided but doesn't match
    # hmac.compare_digest() does a constant-time comparison to prevent
    # timing attacks. Both values must be encoded to bytes first.
    if not hmac.compare_digest(
        x_api_key.encode("utf-8"),
        settings.API_KEY.encode("utf-8"),
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Invalid API key. The provided 'X-API-Key' does not match "
                "the expected value."
            ),
        )

    # Case 3: Key is valid — do nothing, let the request proceed.
    # This function doesn't need to return anything. FastAPI dependencies
    # used in `dependencies=[...]` are run for their side effects (raising
    # exceptions), not their return values.
