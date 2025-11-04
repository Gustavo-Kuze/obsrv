"""
Custom exceptions and error handling for the application.
"""

from typing import Any, Dict, Optional


class APIException(Exception):
    """Base exception for all API errors."""

    def __init__(
        self,
        message: str,
        status_code: int = 500,
        error_code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize API exception.

        Args:
            message: Human-readable error message
            status_code: HTTP status code
            error_code: Machine-readable error code
            details: Additional error details
        """
        self.message = message
        self.status_code = status_code
        self.error_code = error_code or self.__class__.__name__
        self.details = details or {}
        super().__init__(self.message)


class AuthenticationError(APIException):
    """Raised when authentication fails."""

    def __init__(self, message: str = "Authentication failed", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            status_code=401,
            error_code="AUTHENTICATION_ERROR",
            details=details,
        )


class InvalidAPIKeyError(AuthenticationError):
    """Raised when API key is invalid or expired."""

    def __init__(self, message: str = "Invalid or expired API key"):
        super().__init__(message=message)


class RateLimitExceededError(APIException):
    """Raised when rate limit is exceeded."""

    def __init__(self, message: str = "Rate limit exceeded", retry_after: Optional[int] = None):
        details = {"retry_after": retry_after} if retry_after else {}
        super().__init__(
            message=message,
            status_code=429,
            error_code="RATE_LIMIT_EXCEEDED",
            details=details,
        )


class AuthorizationError(APIException):
    """Raised when user lacks required permissions."""

    def __init__(
        self,
        message: str = "Insufficient permissions",
        required_scope: Optional[str] = None,
    ):
        details = {"required_scope": required_scope} if required_scope else {}
        super().__init__(
            message=message,
            status_code=403,
            error_code="AUTHORIZATION_ERROR",
            details=details,
        )


class ValidationError(APIException):
    """Raised when request validation fails."""

    def __init__(self, message: str = "Validation error", errors: Optional[list] = None):
        super().__init__(
            message=message,
            status_code=422,
            error_code="VALIDATION_ERROR",
            details={"errors": errors} if errors else {},
        )


class ResourceNotFoundError(APIException):
    """Raised when requested resource is not found."""

    def __init__(self, resource_type: str, resource_id: Optional[str] = None):
        message = f"{resource_type} not found"
        if resource_id:
            message += f": {resource_id}"
        super().__init__(
            message=message,
            status_code=404,
            error_code="RESOURCE_NOT_FOUND",
            details={"resource_type": resource_type, "resource_id": resource_id},
        )


class DuplicateResourceError(APIException):
    """Raised when attempting to create a duplicate resource."""

    def __init__(self, resource_type: str, identifier: Optional[str] = None):
        message = f"Duplicate {resource_type}"
        if identifier:
            message += f": {identifier}"
        super().__init__(
            message=message,
            status_code=409,
            error_code="DUPLICATE_RESOURCE",
            details={"resource_type": resource_type, "identifier": identifier},
        )


class DatabaseError(APIException):
    """Raised when database operation fails."""

    def __init__(self, message: str = "Database operation failed", original_error: Optional[Exception] = None):
        details = {"original_error": str(original_error)} if original_error else {}
        super().__init__(
            message=message,
            status_code=500,
            error_code="DATABASE_ERROR",
            details=details,
        )


class CrawlError(APIException):
    """Raised when web crawling fails."""

    def __init__(self, message: str = "Crawl operation failed", url: Optional[str] = None):
        super().__init__(
            message=message,
            status_code=500,
            error_code="CRAWL_ERROR",
            details={"url": url} if url else {},
        )


class WebhookError(APIException):
    """Raised when webhook delivery fails."""

    def __init__(
        self,
        message: str = "Webhook delivery failed",
        webhook_url: Optional[str] = None,
        http_status: Optional[int] = None,
    ):
        details = {}
        if webhook_url:
            details["webhook_url"] = webhook_url
        if http_status:
            details["http_status"] = http_status
        super().__init__(
            message=message,
            status_code=500,
            error_code="WEBHOOK_ERROR",
            details=details,
        )


class InngestError(APIException):
    """Raised when Inngest operation fails."""

    def __init__(self, message: str = "Background task operation failed", function_name: Optional[str] = None):
        super().__init__(
            message=message,
            status_code=500,
            error_code="INNGEST_ERROR",
            details={"function_name": function_name} if function_name else {},
        )


class ConfigurationError(APIException):
    """Raised when configuration is invalid."""

    def __init__(self, message: str = "Invalid configuration", config_key: Optional[str] = None):
        super().__init__(
            message=message,
            status_code=500,
            error_code="CONFIGURATION_ERROR",
            details={"config_key": config_key} if config_key else {},
        )


class ExternalServiceError(APIException):
    """Raised when external service call fails."""

    def __init__(
        self,
        message: str = "External service unavailable",
        service_name: Optional[str] = None,
        original_error: Optional[Exception] = None,
    ):
        details = {}
        if service_name:
            details["service_name"] = service_name
        if original_error:
            details["original_error"] = str(original_error)
        super().__init__(
            message=message,
            status_code=503,
            error_code="EXTERNAL_SERVICE_ERROR",
            details=details,
        )
