"""
Product ID extraction utilities with platform-specific patterns and HTML fallbacks.
"""

import re
from typing import Optional, Tuple
from urllib.parse import parse_qs, urlparse

from backend.src.core.logging import get_logger

logger = get_logger(__name__)


class ProductIDExtractor:
    """Extract product IDs from URLs and HTML using platform-specific patterns."""

    # Platform-specific URL patterns
    PATTERNS = {
        "amazon": [
            # Amazon ASIN patterns
            r"/dp/([A-Z0-9]{10})",  # /dp/B08N5WRWNW
            r"/gp/product/([A-Z0-9]{10})",  # /gp/product/B08N5WRWNW
            r"/product/([A-Z0-9]{10})",  # /product/B08N5WRWNW
            r"/ASIN/([A-Z0-9]{10})",  # /ASIN/B08N5WRWNW
            r"[?&]ASIN=([A-Z0-9]{10})",  # ?ASIN=B08N5WRWNW
        ],
        "shopify": [
            # Shopify product ID patterns
            r"/products/([a-z0-9-]+)",  # /products/awesome-t-shirt
            r"/products/([^/?]+)",  # Generic product slug
            r"product_id=(\d+)",  # ?product_id=123456
            r"/products/\d+",  # /products/123456 (numeric)
        ],
        "woocommerce": [
            # WooCommerce patterns
            r"/product/([a-z0-9-]+)",  # /product/awesome-mug
            r"[?&]product_id=(\d+)",  # ?product_id=456
            r"post_id=(\d+)",  # ?post_id=456
        ],
        "magento": [
            # Magento patterns
            r"/catalog/product/view/id/(\d+)",  # Magento 1
            r"/([a-z0-9-]+)\.html",  # Product slug
            r"product/(\d+)",  # Generic product ID
        ],
        "bigcommerce": [
            # BigCommerce patterns
            r"/products/([a-z0-9-]+)",
            r"product_id=(\d+)",
        ],
    }

    @classmethod
    def extract_from_url(cls, url: str) -> Tuple[Optional[str], str]:
        """
        Extract product ID from URL using platform-specific patterns.

        Args:
            url: Product URL

        Returns:
            Tuple of (product_id, extraction_method)
            extraction_method is one of:
            - url_pattern_amazon
            - url_pattern_shopify
            - url_pattern_generic
            - none

        Example:
            >>> ProductIDExtractor.extract_from_url("https://amazon.com/dp/B08N5WRWNW")
            ('B08N5WRWNW', 'url_pattern_amazon')
        """
        try:
            # Try platform-specific patterns
            for platform, patterns in cls.PATTERNS.items():
                for pattern in patterns:
                    match = re.search(pattern, url)
                    if match:
                        product_id = match.group(1) if match.lastindex else match.group(0)
                        method = f"url_pattern_{platform}"
                        logger.debug(
                            "Product ID extracted",
                            extra={
                                "url": url,
                                "product_id": product_id,
                                "method": method,
                            },
                        )
                        return product_id, method

            # Try generic patterns if no platform match
            generic_id, generic_method = cls._extract_generic(url)
            if generic_id:
                return generic_id, generic_method

            logger.debug(
                "No product ID found in URL",
                extra={"url": url},
            )
            return None, "none"

        except Exception as e:
            logger.warning(
                "Product ID extraction failed",
                extra={
                    "url": url,
                    "error": str(e),
                },
            )
            return None, "none"

    @classmethod
    def _extract_generic(cls, url: str) -> Tuple[Optional[str], str]:
        """
        Extract product ID using generic patterns.

        Args:
            url: Product URL

        Returns:
            Tuple of (product_id, extraction_method)
        """
        # Try query parameters first
        parsed = urlparse(url)

        # Common parameter names
        param_names = ["id", "product_id", "productId", "pid", "item_id", "itemId"]
        if parsed.query:
            params = parse_qs(parsed.query)
            for param in param_names:
                if param in params and params[param]:
                    return params[param][0], "url_pattern_generic"

        # Try numeric ID in path
        numeric_match = re.search(r"/(\d{4,})", parsed.path)
        if numeric_match:
            return numeric_match.group(1), "url_pattern_generic"

        # Try slug pattern (last path segment)
        path_segments = [s for s in parsed.path.split("/") if s]
        if path_segments:
            last_segment = path_segments[-1]
            # Remove file extensions
            last_segment = re.sub(r"\.(html?|php|aspx?)$", "", last_segment)
            if last_segment and len(last_segment) > 3:
                return last_segment, "url_pattern_generic"

        return None, "none"

    @classmethod
    def extract_from_html(cls, html: str, url: str) -> Tuple[Optional[str], str]:
        """
        Extract product ID from HTML using meta tags and structured data.

        Args:
            html: HTML content
            url: Product URL (for context)

        Returns:
            Tuple of (product_id, extraction_method)
            extraction_method is one of:
            - html_opengraph
            - html_schema
            - html_meta
            - none

        Example:
            >>> html = '<meta property="product:retailer_item_id" content="ABC123">'
            >>> ProductIDExtractor.extract_from_html(html, "https://example.com")
            ('ABC123', 'html_opengraph')
        """
        try:
            # Try OpenGraph meta tags
            og_patterns = [
                r'<meta\s+property="product:retailer_item_id"\s+content="([^"]+)"',
                r'<meta\s+property="product:sku"\s+content="([^"]+)"',
                r'<meta\s+property="og:product:sku"\s+content="([^"]+)"',
            ]

            for pattern in og_patterns:
                match = re.search(pattern, html, re.IGNORECASE)
                if match:
                    product_id = match.group(1)
                    logger.debug(
                        "Product ID extracted from OpenGraph",
                        extra={
                            "url": url,
                            "product_id": product_id,
                        },
                    )
                    return product_id, "html_opengraph"

            # Try Schema.org structured data
            schema_patterns = [
                r'"sku"\s*:\s*"([^"]+)"',
                r'"productID"\s*:\s*"([^"]+)"',
                r'"identifier"\s*:\s*"([^"]+)"',
            ]

            for pattern in schema_patterns:
                match = re.search(pattern, html)
                if match:
                    product_id = match.group(1)
                    logger.debug(
                        "Product ID extracted from Schema.org",
                        extra={
                            "url": url,
                            "product_id": product_id,
                        },
                    )
                    return product_id, "html_schema"

            # Try standard meta tags
            meta_patterns = [
                r'<meta\s+name="product_id"\s+content="([^"]+)"',
                r'<meta\s+name="sku"\s+content="([^"]+)"',
                r'<meta\s+itemprop="sku"\s+content="([^"]+)"',
                r'<meta\s+itemprop="productID"\s+content="([^"]+)"',
            ]

            for pattern in meta_patterns:
                match = re.search(pattern, html, re.IGNORECASE)
                if match:
                    product_id = match.group(1)
                    logger.debug(
                        "Product ID extracted from meta tag",
                        extra={
                            "url": url,
                            "product_id": product_id,
                        },
                    )
                    return product_id, "html_schema"

            logger.debug(
                "No product ID found in HTML",
                extra={"url": url},
            )
            return None, "none"

        except Exception as e:
            logger.warning(
                "HTML product ID extraction failed",
                extra={
                    "url": url,
                    "error": str(e),
                },
            )
            return None, "none"

    @classmethod
    def extract(cls, url: str, html: Optional[str] = None) -> Tuple[Optional[str], str]:
        """
        Extract product ID using all available methods.

        Tries in order:
        1. URL pattern extraction
        2. HTML extraction (if HTML provided)

        Args:
            url: Product URL
            html: Optional HTML content

        Returns:
            Tuple of (product_id, extraction_method)

        Example:
            >>> ProductIDExtractor.extract(
            ...     "https://shop.example.com/products/awesome-shirt",
            ...     html='<meta property="product:sku" content="SKU123">'
            ... )
            ('awesome-shirt', 'url_pattern_shopify')
        """
        # Try URL first (faster and more reliable)
        product_id, method = cls.extract_from_url(url)
        if product_id:
            return product_id, method

        # Fall back to HTML if provided
        if html:
            product_id, method = cls.extract_from_html(html, url)
            if product_id:
                return product_id, method

        logger.info(
            "Product ID extraction failed for URL",
            extra={"url": url, "had_html": html is not None},
        )
        return None, "none"

    @classmethod
    def detect_platform(cls, url: str) -> Optional[str]:
        """
        Detect e-commerce platform from URL.

        Args:
            url: Website URL

        Returns:
            Platform name or None

        Example:
            >>> ProductIDExtractor.detect_platform("https://amazon.com/dp/B08N5WRWNW")
            'amazon'
        """
        url_lower = url.lower()

        # Direct domain matches
        if "amazon." in url_lower:
            return "amazon"
        if "myshopify.com" in url_lower or "/products/" in url_lower:
            return "shopify"

        # Pattern-based detection
        for platform, patterns in cls.PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, url):
                    return platform

        return None


# Convenience function
def extract_product_id(url: str, html: Optional[str] = None) -> Tuple[Optional[str], str]:
    """
    Extract product ID from URL and/or HTML.

    Args:
        url: Product URL
        html: Optional HTML content

    Returns:
        Tuple of (product_id, extraction_method)

    Example:
        >>> extract_product_id("https://amazon.com/dp/B08N5WRWNW")
        ('B08N5WRWNW', 'url_pattern_amazon')
    """
    return ProductIDExtractor.extract(url, html)


# Export public API
__all__ = [
    "ProductIDExtractor",
    "extract_product_id",
]
