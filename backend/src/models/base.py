"""
Base Pydantic models and response schemas.
"""

from datetime import datetime
from typing import Any, Generic, List, Optional, TypeVar
from uuid import UUID

from pydantic import BaseModel as PydanticBaseModel, ConfigDict, Field


class BaseModel(PydanticBaseModel):
    """Base Pydantic model with common configuration."""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        use_enum_values=False,
        arbitrary_types_allowed=True,
    )


class TimestampMixin(BaseModel):
    """Mixin for models with created_at and updated_at timestamps."""

    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")


class IDMixin(BaseModel):
    """Mixin for models with UUID identifier."""

    id: UUID = Field(..., description="Unique identifier")


# Generic type for paginated data
T = TypeVar("T")


class PaginationMeta(BaseModel):
    """Pagination metadata."""

    page: int = Field(..., description="Current page number", ge=1)
    page_size: int = Field(..., description="Items per page", ge=1, le=500)
    total_items: int = Field(..., description="Total number of items", ge=0)
    total_pages: int = Field(..., description="Total number of pages", ge=0)
    has_next: bool = Field(..., description="Whether there is a next page")
    has_previous: bool = Field(..., description="Whether there is a previous page")


class PaginationResponse(BaseModel, Generic[T]):
    """Generic paginated response wrapper."""

    data: List[T] = Field(..., description="List of items")
    meta: PaginationMeta = Field(..., description="Pagination metadata")


class ErrorDetail(BaseModel):
    """Detailed error information."""

    loc: Optional[List[str]] = Field(None, description="Error location path")
    msg: str = Field(..., description="Error message")
    type: str = Field(..., description="Error type")


class ErrorResponse(BaseModel):
    """Standard error response."""

    detail: str = Field(..., description="Human-readable error message")
    error_code: Optional[str] = Field(None, description="Machine-readable error code")
    errors: Optional[List[ErrorDetail]] = Field(None, description="Validation errors")
    request_id: Optional[str] = Field(None, description="Request correlation ID")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Error timestamp")


class SuccessResponse(BaseModel):
    """Standard success response."""

    message: str = Field(..., description="Success message")
    data: Optional[Any] = Field(None, description="Response data")


class HealthStatus(BaseModel):
    """Health check status."""

    status: str = Field(..., description="Health status (healthy, degraded, unhealthy)")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Check timestamp")


class DetailedHealthStatus(HealthStatus):
    """Detailed health check status with component statuses."""

    components: dict[str, Any] = Field(
        default_factory=dict, description="Component-specific health status"
    )
    version: Optional[str] = Field(None, description="Application version")
    environment: Optional[str] = Field(None, description="Environment name")
