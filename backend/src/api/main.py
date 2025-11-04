"""
FastAPI application factory with CORS, error handlers, and middleware.
"""

import time
from contextlib import asynccontextmanager
from typing import Any, Dict

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.src.api.health import router as health_router
from backend.src.core.config import settings
from backend.src.core.database import close_db, init_db
from backend.src.core.exceptions import APIException
from backend.src.core.logging import (
    clear_request_id,
    get_logger,
    set_request_id,
    setup_logging,
)

# Initialize logging
setup_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager for startup and shutdown events.

    Args:
        app: FastAPI application instance
    """
    # Startup
    logger.info(
        "Starting Obsrv API",
        extra={
            "environment": settings.ENVIRONMENT,
            "debug": settings.DEBUG,
        },
    )

    # Initialize database (optional - Alembic handles migrations)
    # await init_db()

    logger.info("Application started successfully")

    yield

    # Shutdown
    logger.info("Shutting down application")
    await close_db()
    logger.info("Application shutdown complete")


def create_application() -> FastAPI:
    """
    Create and configure FastAPI application.

    Returns:
        Configured FastAPI application
    """
    # Create FastAPI app
    app = FastAPI(
        title="Obsrv API",
        description="E-commerce Monitoring System - Track competitor prices and stock changes",
        version="0.1.0",
        docs_url="/docs" if settings.DEBUG else None,
        redoc_url="/redoc" if settings.DEBUG else None,
        openapi_url="/openapi.json" if settings.DEBUG else None,
        lifespan=lifespan,
    )

    # Configure CORS
    configure_cors(app)

    # Register middleware
    register_middleware(app)

    # Register exception handlers
    register_exception_handlers(app)

    # Register routes
    register_routes(app)

    return app


def configure_cors(app: FastAPI) -> None:
    """
    Configure CORS middleware.

    Args:
        app: FastAPI application
    """
    # Parse CORS origins from settings
    if isinstance(settings.CORS_ORIGINS, str):
        origins = [origin.strip() for origin in settings.CORS_ORIGINS.split(",")]
    else:
        origins = settings.CORS_ORIGINS

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )

    logger.info(
        "CORS configured",
        extra={"allowed_origins": origins},
    )


def register_middleware(app: FastAPI) -> None:
    """
    Register application middleware.

    Args:
        app: FastAPI application
    """

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        """Add request ID to all requests for tracing."""
        # Get or generate request ID
        request_id = request.headers.get("X-Request-ID") or set_request_id()

        # Store in request state
        request.state.request_id = request_id

        # Process request
        response = await call_next(request)

        # Add request ID to response headers
        response.headers["X-Request-ID"] = request_id

        # Clear request ID from context
        clear_request_id()

        return response

    @app.middleware("http")
    async def logging_middleware(request: Request, call_next):
        """Log all requests with timing information."""
        start_time = time.time()

        # Log request
        logger.info(
            "Request started",
            extra={
                "method": request.method,
                "path": request.url.path,
                "client_ip": request.client.host if request.client else None,
            },
        )

        # Process request
        response = await call_next(request)

        # Calculate duration
        duration_ms = round((time.time() - start_time) * 1000, 2)

        # Log response
        logger.info(
            "Request completed",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            },
        )

        # Add duration header
        response.headers["X-Response-Time"] = f"{duration_ms}ms"

        return response

    logger.info("Middleware registered")


def register_exception_handlers(app: FastAPI) -> None:
    """
    Register custom exception handlers.

    Args:
        app: FastAPI application
    """

    @app.exception_handler(APIException)
    async def api_exception_handler(request: Request, exc: APIException):
        """Handle custom API exceptions."""
        logger.warning(
            "API exception occurred",
            extra={
                "error_code": exc.error_code,
                "status_code": exc.status_code,
                "message": exc.message,
                "path": request.url.path,
            },
        )

        return JSONResponse(
            status_code=exc.status_code,
            content={
                "detail": exc.message,
                "error_code": exc.error_code,
                "request_id": getattr(request.state, "request_id", None),
            },
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        """Handle HTTP exceptions."""
        logger.warning(
            "HTTP exception occurred",
            extra={
                "status_code": exc.status_code,
                "detail": exc.detail,
                "path": request.url.path,
            },
        )

        return JSONResponse(
            status_code=exc.status_code,
            content={
                "detail": exc.detail,
                "request_id": getattr(request.state, "request_id", None),
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        """Handle request validation errors."""
        logger.warning(
            "Validation error occurred",
            extra={
                "errors": exc.errors(),
                "path": request.url.path,
            },
        )

        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "detail": "Validation error",
                "errors": exc.errors(),
                "request_id": getattr(request.state, "request_id", None),
            },
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception):
        """Handle unexpected exceptions."""
        logger.error(
            "Unexpected exception occurred",
            extra={
                "error": str(exc),
                "path": request.url.path,
            },
            exc_info=True,
        )

        # Don't expose internal errors in production
        detail = str(exc) if settings.DEBUG else "Internal server error"

        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "detail": detail,
                "error_code": "INTERNAL_SERVER_ERROR",
                "request_id": getattr(request.state, "request_id", None),
            },
        )

    logger.info("Exception handlers registered")


def register_routes(app: FastAPI) -> None:
    """
    Register API routes.

    Args:
        app: FastAPI application
    """
    # Health check routes (no /v1 prefix)
    app.include_router(health_router)

    # API v1 routes will be added here as they're implemented
    # Example:
    # app.include_router(websites_router, prefix="/v1")
    # app.include_router(products_router, prefix="/v1")
    # app.include_router(auth_router, prefix="/v1")

    logger.info("Routes registered")


# Create application instance
app = create_application()


# Root endpoint
@app.get("/", tags=["Root"])
async def root() -> Dict[str, Any]:
    """
    Root endpoint with API information.

    Returns:
        API information
    """
    return {
        "name": "Obsrv API",
        "version": "0.1.0",
        "description": "E-commerce Monitoring System",
        "environment": settings.ENVIRONMENT,
        "docs": "/docs" if settings.DEBUG else None,
        "health": "/health",
    }


# Export app
__all__ = ["app", "create_application"]
