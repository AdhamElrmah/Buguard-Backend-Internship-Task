"""
Global exception handlers for the FastAPI application.

These handlers intercept exceptions BEFORE FastAPI's default handler and
return a consistent JSON error response. Without them, different error
types produce different response shapes, which makes life hard for API
consumers.

The consistent error format:
    {
        "detail": {
            "error": "not_found",              # machine-readable code
            "message": "Asset ... not found",   # human-readable description
            "status_code": 404                  # HTTP status code
        }
    }

Why wrap everything in "detail"?
    FastAPI's default HTTPException uses "detail" as the top-level key.
    By keeping the same key, clients that already handle FastAPI errors
    don't need major changes — they just parse the richer structure.

Handler registration order matters:
    Python/Starlette matches exception handlers from most specific to
    least specific. We register:
      1. DarkAtlasException  → our custom business errors
      2. RequestValidationError → Pydantic validation (bad request body)
      3. Exception            → catch-all for unhandled errors

How to register (in main.py):
    from app.core.error_handlers import register_error_handlers
    register_error_handlers(app)
"""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.exceptions import DarkAtlasException

# Logger for recording unhandled errors.
# We use the module path so log output shows where the error was caught.
logger = logging.getLogger(__name__)


async def darkatlas_exception_handler(
    request: Request, exc: DarkAtlasException
) -> JSONResponse:
    """
    Handle all DarkAtlasException subclasses (NotFoundException,
    ConflictException, ValidationException, AuthenticationException,
    AuthorizationException).

    Each exception carries its own status_code, error_code, and message.
    We just read those attributes and format the response.

    Example output for NotFoundException:
        HTTP 404
        {
            "detail": {
                "error": "not_found",
                "message": "Asset with id '...' not found",
                "status_code": 404
            }
        }
    """
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": {
                "error": exc.error_code,
                "message": exc.message,
                "status_code": exc.status_code,
            }
        },
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """
    Handle Pydantic validation errors (malformed request body/params).

    When does this fire?
        - Client sends wrong field types (e.g., string instead of UUID)
        - Client omits required fields
        - Client sends invalid enum values
        - Path parameter fails validation (e.g., "abc" as a UUID)

    FastAPI's default handler returns 422 with a list of error objects.
    We wrap it in our consistent format while preserving the detailed
    error list in the message field.

    Example output:
        HTTP 422
        {
            "detail": {
                "error": "validation_error",
                "message": [
                    {
                        "loc": ["body", "type"],
                        "msg": "Input should be ...",
                        "type": "enum"
                    }
                ],
                "status_code": 422
            }
        }
    """
    return JSONResponse(
        status_code=422,
        content={
            "detail": {
                "error": "validation_error",
                "message": exc.errors(),
                "status_code": 422,
            }
        },
    )


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Catch-all handler for any unhandled exception.

    Why is this critical?
        Without it, an unhandled exception (like a database crash, a
        bug in our code, etc.) would return a stack trace to the client.
        Stack traces leak internal details — file paths, library versions,
        database table names — that attackers can exploit.

    This handler:
        1. Logs the full error (with traceback) for developers to debug.
        2. Returns a generic "Internal server error" message to the client
           with NO internal details.

    Example output:
        HTTP 500
        {
            "detail": {
                "error": "internal_error",
                "message": "An unexpected error occurred. Please try again later.",
                "status_code": 500
            }
        }
    """
    # Log the full exception with traceback for debugging.
    # This goes to the server logs, NOT to the client.
    logger.error(
        "Unhandled exception on %s %s",
        request.method,
        request.url.path,
        exc_info=exc,
    )

    return JSONResponse(
        status_code=500,
        content={
            "detail": {
                "error": "internal_error",
                "message": "An unexpected error occurred. Please try again later.",
                "status_code": 500,
            }
        },
    )


def register_error_handlers(app: FastAPI) -> None:
    """
    Register all exception handlers on the FastAPI app instance.

    Called once in main.py during app initialization.

    Why a function instead of decorators?
        FastAPI's @app.exception_handler() decorator requires the app
        instance at import time. By using a function, we can call it
        after the app is created, keeping main.py clean and avoiding
        circular imports.

    Registration order:
        More specific exceptions first, generic last. Starlette
        matches handlers from most specific to least specific.
    """
    # 1. Our custom business exceptions (most specific)
    app.add_exception_handler(DarkAtlasException, darkatlas_exception_handler)

    # 2. Pydantic validation errors (FastAPI's built-in 422 errors)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)

    # 3. Catch-all for anything we didn't anticipate (least specific)
    app.add_exception_handler(Exception, generic_exception_handler)
