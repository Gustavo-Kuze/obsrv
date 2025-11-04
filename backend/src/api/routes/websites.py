"""
Website management API endpoints.
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.src.api.schemas.website_schemas import (
    ApproveProductsRequest,
    ApproveProductsResponse,
    DiscoveredProductsResponse,
    Website,
    WebsiteListResponse,
    WebsiteRegistrationRequest,
    WebsiteRegistrationResponse,
    WebsiteUpdateRequest,
)
from backend.src.core.auth import AuthenticatedClient, get_current_client, require_write
from backend.src.core.config import settings
from backend.src.core.database import get_db
from backend.src.core.exceptions import (
    DuplicateResourceError,
    ResourceNotFoundError,
    ValidationError,
)
from backend.src.core.logging import get_logger
from backend.src.services.website_service import website_service

logger = get_logger(__name__)

router = APIRouter(prefix="/v1/websites", tags=["Websites"])


@router.post(
    "",
    response_model=WebsiteRegistrationResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Register a new website for monitoring",
    dependencies=[Depends(require_write)],
)
async def register_website(
    request: WebsiteRegistrationRequest,
    client: AuthenticatedClient = Depends(get_current_client),
    db: AsyncSession = Depends(get_db),
) -> WebsiteRegistrationResponse:
    """
    Register a new e-commerce website for monitoring.

    This endpoint:
    1. Validates the website URL and configuration
    2. Creates a website record in pending_approval status
    3. Triggers background product discovery from seed URLs
    4. Returns immediately with 202 Accepted

    The product discovery runs asynchronously. Use the discovery_job_id
    to track progress via Inngest dashboard.

    Example:
        ```bash
        curl -X POST http://localhost:8000/v1/websites \\
          -H "X-API-Key: your-key" \\
          -H "Content-Type: application/json" \\
          -d '{
            "base_url": "https://shop.example.com",
            "seed_urls": ["https://shop.example.com/products"],
            "crawl_frequency_minutes": 1440,
            "price_change_threshold_pct": 1.0,
            "webhook_endpoint_url": "https://your-server.com/webhook"
          }'
        ```
    """
    try:
        website, discovery_job_id = await website_service.register_website(
            client_id=client.client_id,
            base_url=request.base_url,
            seed_urls=request.seed_urls,
            crawl_frequency_minutes=request.crawl_frequency_minutes,
            price_change_threshold_pct=request.price_change_threshold_pct,
            retention_days=request.retention_days,
            webhook_endpoint_url=request.webhook_endpoint_url,
            webhook_enabled=request.webhook_enabled,
            db=db,
        )

        return WebsiteRegistrationResponse(
            website_id=website.id,
            status=website.status,
            message="Website registered successfully. Product discovery in progress.",
            discovery_job_id=discovery_job_id,
        )

    except DuplicateResourceError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=e.message,
        )
    except Exception as e:
        logger.error(
            "Website registration failed",
            extra={"error": str(e)},
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to register website",
        )


@router.get(
    "",
    response_model=WebsiteListResponse,
    summary="List monitored websites",
)
async def list_websites(
    status_filter: Optional[str] = Query(
        None,
        alias="status",
        description="Filter by status (pending_approval, active, paused, failed)",
    ),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(
        settings.DEFAULT_PAGE_SIZE,
        ge=1,
        le=settings.MAX_PAGE_SIZE,
        description="Items per page",
    ),
    client: AuthenticatedClient = Depends(get_current_client),
    db: AsyncSession = Depends(get_db),
) -> WebsiteListResponse:
    """
    List all monitored websites for the authenticated client.

    Supports pagination and filtering by status.

    Example:
        ```bash
        curl -H "X-API-Key: your-key" \\
          "http://localhost:8000/v1/websites?status=active&page=1&page_size=10"
        ```
    """
    websites, total = await website_service.list_websites(
        client_id=client.client_id,
        status=status_filter,
        page=page,
        page_size=page_size,
        db=db,
    )

    return WebsiteListResponse(
        websites=[Website.model_validate(w) for w in websites],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/{website_id}",
    response_model=Website,
    summary="Get website details",
)
async def get_website(
    website_id: UUID,
    client: AuthenticatedClient = Depends(get_current_client),
    db: AsyncSession = Depends(get_db),
) -> Website:
    """
    Get details for a specific monitored website.

    Validates that the website belongs to the authenticated client.

    Example:
        ```bash
        curl -H "X-API-Key: your-key" \\
          http://localhost:8000/v1/websites/<website-id>
        ```
    """
    try:
        website = await website_service.get_website(
            website_id=website_id,
            client_id=client.client_id,
            db=db,
        )
        return Website.model_validate(website)

    except ResourceNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=e.message,
        )


@router.patch(
    "/{website_id}",
    response_model=Website,
    summary="Update website settings",
    dependencies=[Depends(require_write)],
)
async def update_website(
    website_id: UUID,
    request: WebsiteUpdateRequest,
    client: AuthenticatedClient = Depends(get_current_client),
    db: AsyncSession = Depends(get_db),
) -> Website:
    """
    Update website monitoring settings.

    Only provided fields will be updated.

    Example:
        ```bash
        curl -X PATCH http://localhost:8000/v1/websites/<website-id> \\
          -H "X-API-Key: your-key" \\
          -H "Content-Type: application/json" \\
          -d '{
            "crawl_frequency_minutes": 720,
            "price_change_threshold_pct": 2.0
          }'
        ```
    """
    try:
        updates = request.model_dump(exclude_unset=True)
        website = await website_service.update_website(
            website_id=website_id,
            client_id=client.client_id,
            updates=updates,
            db=db,
        )
        return Website.model_validate(website)

    except ResourceNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=e.message,
        )


@router.delete(
    "/{website_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete website",
    dependencies=[Depends(require_write)],
)
async def delete_website(
    website_id: UUID,
    client: AuthenticatedClient = Depends(get_current_client),
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Delete a monitored website and all associated data.

    This will cascade delete:
    - All products
    - All crawl logs
    - All historical data

    This action cannot be undone!

    Example:
        ```bash
        curl -X DELETE http://localhost:8000/v1/websites/<website-id> \\
          -H "X-API-Key: your-key"
        ```
    """
    try:
        await website_service.delete_website(
            website_id=website_id,
            client_id=client.client_id,
            db=db,
        )

    except ResourceNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=e.message,
        )


@router.get(
    "/{website_id}/discovered-products",
    response_model=DiscoveredProductsResponse,
    summary="Get discovered products awaiting approval",
)
async def get_discovered_products(
    website_id: UUID,
    client: AuthenticatedClient = Depends(get_current_client),
    db: AsyncSession = Depends(get_db),
) -> DiscoveredProductsResponse:
    """
    Get products discovered from seed URLs, awaiting approval.

    After registering a website, product discovery runs in the background.
    Once complete, this endpoint returns the discovered products.

    You must then call the approve-products endpoint to select which
    products to monitor (up to 100).

    Example:
        ```bash
        curl -H "X-API-Key: your-key" \\
          http://localhost:8000/v1/websites/<website-id>/discovered-products
        ```
    """
    try:
        discovered_data = await website_service.get_discovered_products(
            website_id=website_id,
            client_id=client.client_id,
            db=db,
        )

        products = discovered_data.get("products", [])

        return DiscoveredProductsResponse(
            website_id=website_id,
            discovered_count=len(products),
            products=products,
            max_allowed=100,
        )

    except ResourceNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=e.message,
        )


@router.post(
    "/{website_id}/approve-products",
    response_model=ApproveProductsResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Approve discovered products for monitoring",
    dependencies=[Depends(require_write)],
)
async def approve_products(
    website_id: UUID,
    request: ApproveProductsRequest,
    client: AuthenticatedClient = Depends(get_current_client),
    db: AsyncSession = Depends(get_db),
) -> ApproveProductsResponse:
    """
    Approve discovered products to start monitoring.

    This endpoint:
    1. Validates the product URLs are from the discovered list
    2. Ensures product count doesn't exceed 100
    3. Triggers baseline crawl to establish initial data
    4. Updates website status to 'active'

    The baseline crawl runs asynchronously. Use the baseline_crawl_job_id
    to track progress.

    Example:
        ```bash
        curl -X POST http://localhost:8000/v1/websites/<website-id>/approve-products \\
          -H "X-API-Key: your-key" \\
          -H "Content-Type: application/json" \\
          -d '{
            "product_urls": [
              "https://shop.example.com/product/123",
              "https://shop.example.com/product/456"
            ]
          }'
        ```
    """
    try:
        baseline_job_id = await website_service.approve_products(
            website_id=website_id,
            client_id=client.client_id,
            product_urls=request.product_urls,
            db=db,
        )

        return ApproveProductsResponse(
            website_id=website_id,
            approved_count=len(request.product_urls),
            message="Products approved successfully. Baseline crawl in progress.",
            baseline_crawl_job_id=baseline_job_id,
        )

    except ResourceNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=e.message,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


# Export router
__all__ = ["router"]
