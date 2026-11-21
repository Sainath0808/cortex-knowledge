"""Domain exceptions mapped to HTTP responses in main.py exception handlers."""


class CortexError(Exception):
    """Base class for all domain errors."""

    status_code = 500
    detail = "Internal server error"

    def __init__(self, detail: str | None = None):
        if detail:
            self.detail = detail
        super().__init__(self.detail)


class AuthError(CortexError):
    status_code = 401
    detail = "Not authenticated"


class PermissionDenied(CortexError):
    status_code = 403
    detail = "Permission denied"


class NotFound(CortexError):
    status_code = 404
    detail = "Resource not found"


class InvalidRequest(CortexError):
    status_code = 400
    detail = "Invalid request"


class UnsupportedMediaType(CortexError):
    status_code = 415
    detail = "Unsupported document type"


class PayloadTooLarge(CortexError):
    status_code = 413
    detail = "Uploaded document is too large"


class RateLimited(CortexError):
    status_code = 429
    detail = "Rate limit exceeded"


class GuardrailViolation(CortexError):
    """Input blocked by safety guardrails (e.g., prompt injection)."""

    status_code = 400
    detail = "Request blocked by content guardrails"


class UpstreamAIError(CortexError):
    """LLM / embedding provider failure after retries were exhausted."""

    status_code = 502
    detail = "AI provider is unavailable, please retry"
