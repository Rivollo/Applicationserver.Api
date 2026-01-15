from typing import Any, Optional


class AppException(Exception):
    """Base exception for all application-specific errors."""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 400,
        details: Optional[Any] = None,
    ):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details
        super().__init__(self.message)


class NotFoundException(AppException):
    """Exception raised when a resource is not found."""

    def __init__(self, message: str = "Resource not found", details: Optional[Any] = None):
        super().__init__(
            code="NOT_FOUND",
            message=message,
            status_code=404,
            details=details,
        )


class ValidationException(AppException):
    """Exception raised when validation fails."""

    def __init__(self, message: str = "Validation failed", details: Optional[Any] = None):
        super().__init__(
            code="VALIDATION_ERROR",
            message=message,
            status_code=400,
            details=details,
        )


class DatabaseException(AppException):
    """Exception raised for database-related errors."""

    def __init__(
        self, message: str = "Database error occurred", details: Optional[Any] = None
    ):
        super().__init__(
            code="DATABASE_ERROR",
            message=message,
            status_code=500,
            details=details,
        )


class UnauthorizedException(AppException):
    """Exception raised when authentication or authorization fails."""

    def __init__(self, message: str = "Unauthorized access", details: Optional[Any] = None):
        super().__init__(
            code="UNAUTHORIZED",
            message=message,
            status_code=401,
            details=details,
        )
