"""
Custom exception classes for the DarkAtlas application.

Why custom exceptions instead of FastAPI's HTTPException?

1. **Separation of concerns** — The service layer should not know about HTTP.
   HTTPException is an HTTP-specific concept (it knows about status codes,
   headers, etc.). Our service layer deals with *business logic*, not HTTP.
   Custom exceptions express business-level problems:
     - "this thing was not found" (NotFoundException)
     - "this thing already exists" (ConflictException)
     - "this input is invalid" (ValidationException)

2. **Consistent error format** — With HTTPException, every raise site defines
   its own error shape. With custom exceptions + a central error handler, ALL
   errors share the exact same JSON structure. API consumers can write one
   error-parsing function and it works for every endpoint.

3. **Testability** — Tests can catch NotFoundException without importing
   FastAPI. The service layer becomes a pure Python module that raises
   Python exceptions.

4. **Reusability** — If we ever add a CLI, a background worker, or a gRPC
   interface, these exceptions still make sense. HTTPException does not.

The error response format (handled in error_handlers.py):
    {
        "detail": {
            "error": "not_found",          # machine-readable error code
            "message": "Asset ... not found",  # human-readable message
            "status_code": 404             # HTTP status code
        }
    }
"""


class DarkAtlasException(Exception):
    """
    Base exception for all DarkAtlas business errors.

    All custom exceptions inherit from this. This lets us write a single
    catch-all handler for DarkAtlas errors if needed:

        try:
            ...
        except DarkAtlasException as e:
            # handle any business error

    Attributes:
        message:     Human-readable error description for the API consumer.
        error_code:  Machine-readable error identifier (e.g., "not_found").
                     Clients can switch/match on this string to handle
                     specific errors programmatically.
        status_code: The HTTP status code that the error handler will use.
                     Stored here for convenience — the error handler reads
                     this to set the response status code.
    """

    def __init__(
        self,
        message: str,
        error_code: str = "internal_error",
        status_code: int = 500,
    ):
        self.message = message
        self.error_code = error_code
        self.status_code = status_code
        super().__init__(self.message)


class NotFoundException(DarkAtlasException):
    """
    Raised when a requested resource does not exist.

    Examples:
        - GET /assets/{id} where id doesn't exist
        - DELETE /relationships/{id} where id doesn't exist
        - Creating a relationship referencing a non-existent asset

    Maps to HTTP 404 Not Found.
    """

    def __init__(self, message: str):
        super().__init__(
            message=message,
            error_code="not_found",
            status_code=404,
        )


class ConflictException(DarkAtlasException):
    """
    Raised when an operation conflicts with the current state.

    Examples:
        - Creating a relationship that already exists (same source,
          target, and type)

    Maps to HTTP 409 Conflict.
    """

    def __init__(self, message: str):
        super().__init__(
            message=message,
            error_code="conflict",
            status_code=409,
        )


class ValidationException(DarkAtlasException):
    """
    Raised when business-level validation fails.

    This is different from Pydantic validation errors (which are caught
    separately). Pydantic catches schema-level issues (wrong type, missing
    field). This exception catches business-level issues that Pydantic
    can't know about (e.g., "threshold_days must be positive").

    Maps to HTTP 422 Unprocessable Entity.
    """

    def __init__(self, message: str):
        super().__init__(
            message=message,
            error_code="validation_error",
            status_code=422,
        )


class AuthenticationException(DarkAtlasException):
    """
    Raised when authentication credentials are missing.

    Example:
        - A write request without the X-API-Key header.

    Maps to HTTP 401 Unauthorized.
    """

    def __init__(self, message: str):
        super().__init__(
            message=message,
            error_code="unauthorized",
            status_code=401,
        )


class AuthorizationException(DarkAtlasException):
    """
    Raised when authentication credentials are present but invalid.

    Example:
        - A write request with an incorrect X-API-Key value.

    Maps to HTTP 403 Forbidden.
    """

    def __init__(self, message: str):
        super().__init__(
            message=message,
            error_code="forbidden",
            status_code=403,
        )
