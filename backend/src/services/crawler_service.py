"""
Crawl4ai integration service for web crawling with rate limiting and retry logic.
"""

import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from backend.src.core.config import settings
from backend.src.core.exceptions import CrawlError
from backend.src.core.logging import get_logger
from backend.src.core.product_extractors import extract_product_id
from backend.src.core.url_utils import extract_domain, normalize_url

logger = get_logger(__name__)

# Rate limiting: track last request time per domain
_domain_last_request: Dict[str, float] = {}
_rate_limit_seconds = 60.0 / settings.CRAWL_RATE_LIMIT_PER_DOMAIN  # seconds between requests


class CrawlerService:
    """Service for crawling websites using crawl4ai."""

    def __init__(self):
        """Initialize crawler service."""
        self.timeout = settings.DEFAULT_CRAWL_TIMEOUT
        self.retry_attempts = settings.CRAWL_RETRY_ATTEMPTS
        self.retry_backoff_base = settings.CRAWL_RETRY_BACKOFF_BASE

    async def _rate_limit(self, domain: str) -> None:
        """
        Enforce rate limiting per domain.

        Args:
            domain: Domain to rate limit
        """
        import time

        now = time.time()
        last_request = _domain_last_request.get(domain, 0)
        elapsed = now - last_request

        if elapsed < _rate_limit_seconds:
            wait_time = _rate_limit_seconds - elapsed
            logger.debug(
                f"Rate limiting: waiting {wait_time:.2f}s for {domain}",
                extra={"domain": domain, "wait_time": wait_time},
            )
            await asyncio.sleep(wait_time)

        _domain_last_request[domain] = time.time()

    async def crawl_url(
        self,
        url: str,
        extract_links: bool = False,
        retry_count: int = 0,
    ) -> Dict[str, Any]:
        """
        Crawl a single URL and extract content.

        Args:
            url: URL to crawl
            extract_links: Whether to extract links from the page
            retry_count: Current retry attempt number

        Returns:
            Dictionary with crawl results

        Raises:
            CrawlError: If crawl fails after retries
        """
        domain = extract_domain(url)
        if not domain:
            raise CrawlError(f"Invalid URL: {url}", url=url)

        # Rate limiting
        await self._rate_limit(domain)

        try:
            # For MVP, we'll use a simple HTTP client approach
            # In production, you'd use actual crawl4ai with AsyncPlaywrightCrawlerStrategy
            import httpx

            logger.info(
                "Crawling URL",
                extra={"url": url, "retry_count": retry_count},
            )

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    url,
                    headers={
                        "User-Agent": "Mozilla/5.0 (compatible; ObsrvBot/1.0; +https://obsrv.example.com/bot)",
                        "Accept": "text/html,application/xhtml+xml,application/xml",
                    },
                    follow_redirects=True,
                )

                if response.status_code != 200:
                    raise CrawlError(
                        f"HTTP {response.status_code} for {url}",
                        url=url,
                    )

                html = response.text
                final_url = str(response.url)

                result = {
                    "url": url,
                    "final_url": final_url,
                    "status_code": response.status_code,
                    "html": html,
                    "html_length": len(html),
                    "crawled_at": datetime.utcnow(),
                }

                # Extract links if requested
                if extract_links:
                    result["links"] = await self._extract_links(html, final_url)

                logger.info(
                    "URL crawled successfully",
                    extra={
                        "url": url,
                        "status_code": response.status_code,
                        "html_length": len(html),
                    },
                )

                return result

        except Exception as e:
            logger.warning(
                "Crawl failed",
                extra={
                    "url": url,
                    "retry_count": retry_count,
                    "error": str(e),
                },
            )

            # Retry logic
            if retry_count < self.retry_attempts:
                backoff_seconds = self.retry_backoff_base * (2**retry_count)
                logger.info(
                    f"Retrying after {backoff_seconds}s",
                    extra={"url": url, "backoff_seconds": backoff_seconds},
                )
                await asyncio.sleep(backoff_seconds)
                return await self.crawl_url(url, extract_links, retry_count + 1)

            # All retries exhausted
            raise CrawlError(
                f"Failed to crawl {url} after {self.retry_attempts} attempts: {str(e)}",
                url=url,
            ) from e

    async def _extract_links(self, html: str, base_url: str) -> List[str]:
        """
        Extract links from HTML.

        Args:
            html: HTML content
            base_url: Base URL for resolving relative links

        Returns:
            List of absolute URLs
        """
        from urllib.parse import urljoin

        import re

        # Simple link extraction using regex
        # In production, use a proper HTML parser
        link_pattern = r'<a[^>]+href=["\']([^"\']+)["\']'
        matches = re.findall(link_pattern, html, re.IGNORECASE)

        links = []
        for href in matches:
            # Convert to absolute URL
            absolute_url = urljoin(base_url, href)
            # Normalize
            normalized = normalize_url(absolute_url)
            if normalized and normalized.startswith(("http://", "https://")):
                links.append(normalized)

        # Deduplicate
        return list(set(links))

    async def crawl_product(self, url: str) -> Dict[str, Any]:
        """
        Crawl a product page and extract data.

        Args:
            url: Product URL

        Returns:
            Dictionary with product data

        Raises:
            CrawlError: If crawl fails
        """
        result = await self.crawl_url(url, extract_links=False)
        html = result["html"]

        # Extract product ID
        product_id, extraction_method = extract_product_id(url, html)

        # Extract product data from HTML
        # In production, use proper selectors for each e-commerce platform
        product_data = {
            "url": url,
            "normalized_url": normalize_url(url),
            "product_id": product_id,
            "extraction_method": extraction_method,
            "product_name": await self._extract_product_name(html),
            "price": await self._extract_price(html),
            "currency": "USD",  # TODO: Extract from page
            "stock_status": await self._extract_stock_status(html),
            "raw_html": html[:10000],  # Store first 10KB for debugging
            "crawled_at": result["crawled_at"],
        }

        logger.info(
            "Product crawled",
            extra={
                "url": url,
                "product_id": product_id,
                "price": product_data["price"],
                "stock_status": product_data["stock_status"],
            },
        )

        return product_data

    async def _extract_product_name(self, html: str) -> Optional[str]:
        """Extract product name from HTML."""
        import re

        # Try common patterns
        patterns = [
            r'<meta\s+property="og:title"\s+content="([^"]+)"',
            r'<title>([^<]+)</title>',
            r'<h1[^>]*>([^<]+)</h1>',
        ]

        for pattern in patterns:
            match = re.search(pattern, html, re.IGNORECASE)
            if match:
                return match.group(1).strip()

        return None

    async def _extract_price(self, html: str) -> Optional[float]:
        """Extract price from HTML."""
        import re

        # Try common patterns
        patterns = [
            r'"price":\s*"?(\d+\.?\d*)"?',
            r'<meta\s+property="product:price:amount"\s+content="([^"]+)"',
            r'\$(\d+\.\d{2})',
        ]

        for pattern in patterns:
            match = re.search(pattern, html)
            if match:
                try:
                    return float(match.group(1))
                except ValueError:
                    continue

        return None

    async def _extract_stock_status(self, html: str) -> str:
        """Extract stock status from HTML."""
        html_lower = html.lower()

        if any(phrase in html_lower for phrase in ["out of stock", "sold out", "unavailable"]):
            return "out_of_stock"
        elif any(phrase in html_lower for phrase in ["in stock", "available", "add to cart"]):
            return "in_stock"
        elif "limited" in html_lower or "only.*left" in html_lower:
            return "limited_availability"

        return "unknown"


# Global instance
crawler_service = CrawlerService()
