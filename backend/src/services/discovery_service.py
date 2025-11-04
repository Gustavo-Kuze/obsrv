"""
Product discovery service for finding products from seed URLs.
"""

import re
from typing import Any, Dict, List
from urllib.parse import urlparse

from backend.src.core.logging import get_logger
from backend.src.core.product_extractors import ProductIDExtractor
from backend.src.core.url_utils import clean_url_for_comparison, is_same_domain, normalize_url
from backend.src.services.crawler_service import crawler_service

logger = get_logger(__name__)


class ProductDiscoveryService:
    """Service for discovering products from seed URLs."""

    # Common e-commerce URL patterns
    PRODUCT_URL_PATTERNS = [
        r'/product[s]?/',
        r'/item[s]?/',
        r'/p/',
        r'/dp/',
        r'/gp/product/',
        r'-p-\d+',
        r'/pd/',
    ]

    # URL patterns to exclude (category pages, etc.)
    EXCLUDE_PATTERNS = [
        r'/category/',
        r'/categories/',
        r'/collection[s]?/',
        r'/search',
        r'/cart',
        r'/checkout',
        r'/account',
        r'/login',
        r'/register',
        r'/blog',
        r'/about',
        r'/contact',
    ]

    async def discover_products(
        self,
        base_url: str,
        seed_urls: List[str],
        max_products: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Discover products from seed URLs.

        Args:
            base_url: Base URL of the website
            seed_urls: List of seed URLs to crawl
            max_products: Maximum number of products to discover

        Returns:
            List of discovered product dictionaries

        Example:
            >>> products = await discover_products(
            ...     "https://shop.example.com",
            ...     ["https://shop.example.com/products"],
            ...     max_products=50
            ... )
        """
        logger.info(
            "Starting product discovery",
            extra={
                "base_url": base_url,
                "seed_count": len(seed_urls),
                "max_products": max_products,
            },
        )

        discovered_urls = set()
        products = []

        # Crawl each seed URL
        for seed_url in seed_urls:
            if len(products) >= max_products:
                break

            try:
                # Crawl seed URL and extract links
                result = await crawler_service.crawl_url(seed_url, extract_links=True)
                links = result.get("links", [])

                logger.info(
                    "Extracted links from seed URL",
                    extra={
                        "seed_url": seed_url,
                        "links_count": len(links),
                    },
                )

                # Filter and rank links
                product_links = self._filter_product_links(links, base_url)

                for link in product_links:
                    if len(products) >= max_products:
                        break

                    # Skip duplicates
                    clean_link = clean_url_for_comparison(link)
                    if clean_link in discovered_urls:
                        continue

                    discovered_urls.add(clean_link)

                    # Extract product info
                    product_info = await self._extract_product_info(link, base_url)
                    if product_info:
                        products.append(product_info)

            except Exception as e:
                logger.warning(
                    "Failed to process seed URL",
                    extra={
                        "seed_url": seed_url,
                        "error": str(e),
                    },
                )
                continue

        # Rank products by relevance
        ranked_products = self._rank_products(products)

        logger.info(
            "Product discovery completed",
            extra={
                "discovered_count": len(ranked_products),
                "max_products": max_products,
            },
        )

        return ranked_products[:max_products]

    def _filter_product_links(self, links: List[str], base_url: str) -> List[str]:
        """
        Filter links to identify product URLs.

        Args:
            links: List of URLs to filter
            base_url: Base URL to filter against

        Returns:
            Filtered list of product URLs
        """
        product_links = []

        for link in links:
            # Must be same domain
            if not is_same_domain(link, base_url):
                continue

            # Check if matches product pattern
            if self._is_product_url(link):
                # Check if doesn't match exclude pattern
                if not self._is_excluded_url(link):
                    product_links.append(link)

        return product_links

    def _is_product_url(self, url: str) -> bool:
        """Check if URL matches product URL patterns."""
        for pattern in self.PRODUCT_URL_PATTERNS:
            if re.search(pattern, url, re.IGNORECASE):
                return True

        # Also check if product ID can be extracted
        product_id, method = ProductIDExtractor.extract_from_url(url)
        return product_id is not None and method != "none"

    def _is_excluded_url(self, url: str) -> bool:
        """Check if URL matches exclusion patterns."""
        for pattern in self.EXCLUDE_PATTERNS:
            if re.search(pattern, url, re.IGNORECASE):
                return True
        return False

    async def _extract_product_info(
        self,
        url: str,
        base_url: str,
    ) -> Dict[str, Any] | None:
        """
        Extract basic product information.

        Args:
            url: Product URL
            base_url: Base website URL

        Returns:
            Product info dictionary or None if extraction fails
        """
        try:
            # For discovery, we don't need to crawl each product
            # Just extract what we can from the URL
            normalized = normalize_url(url)
            product_id, extraction_method = ProductIDExtractor.extract_from_url(url)

            if not product_id:
                # If we can't extract ID, skip this product
                return None

            product_info = {
                "url": url,
                "normalized_url": normalized,
                "product_id": product_id,
                "extraction_method": extraction_method,
                "name": None,  # Will be extracted during baseline crawl
                "relevance_score": self._calculate_relevance(url, base_url),
            }

            return product_info

        except Exception as e:
            logger.debug(
                "Failed to extract product info",
                extra={"url": url, "error": str(e)},
            )
            return None

    def _calculate_relevance(self, url: str, base_url: str) -> float:
        """
        Calculate relevance score for a product URL.

        Higher scores for:
        - Shorter URLs (simpler paths)
        - URLs with clear product indicators
        - URLs with extractable product IDs

        Args:
            url: Product URL
            base_url: Base URL

        Returns:
            Relevance score between 0.0 and 1.0
        """
        score = 0.5  # Base score

        parsed = urlparse(url)
        path = parsed.path

        # Shorter paths are often more relevant
        path_segments = [s for s in path.split("/") if s]
        if len(path_segments) <= 3:
            score += 0.2
        elif len(path_segments) <= 5:
            score += 0.1

        # Check for strong product indicators
        strong_indicators = ["/product/", "/p/", "/dp/", "/item/"]
        if any(indicator in path.lower() for indicator in strong_indicators):
            score += 0.2

        # Product ID extraction method
        _, method = ProductIDExtractor.extract_from_url(url)
        if "amazon" in method or "shopify" in method:
            score += 0.1

        # Normalize to 0-1 range
        return min(1.0, max(0.0, score))

    def _rank_products(self, products: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Rank products by relevance score.

        Args:
            products: List of product dictionaries

        Returns:
            Sorted list of products (highest relevance first)
        """
        return sorted(
            products,
            key=lambda p: p.get("relevance_score", 0.0),
            reverse=True,
        )


# Global instance
discovery_service = ProductDiscoveryService()
