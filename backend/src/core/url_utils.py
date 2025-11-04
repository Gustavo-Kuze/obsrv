"""
URL normalization and cleaning utilities using url-normalize and w3lib.
"""

import re
from typing import Optional, Set
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from url_normalize import url_normalize
from w3lib.url import canonicalize_url, url_query_cleaner

from backend.src.core.logging import get_logger

logger = get_logger(__name__)

# Common tracking parameters to remove
TRACKING_PARAMS: Set[str] = {
    # Google Analytics
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "utm_id",
    "utm_source_platform",
    "utm_creative_format",
    "utm_marketing_tactic",
    # Facebook
    "fbclid",
    "fb_action_ids",
    "fb_action_types",
    "fb_ref",
    "fb_source",
    # Other common tracking
    "gclid",  # Google Click ID
    "dclid",  # DoubleClick ID
    "msclkid",  # Microsoft Click ID
    "mc_eid",  # Mailchimp
    "mc_cid",  # Mailchimp
    "_ga",  # Google Analytics
    "_gl",  # Google Linker
    # Amazon specific
    "ref",
    "ref_",
    "pf_rd_p",
    "pf_rd_r",
    "pf_rd_s",
    "pf_rd_t",
    "pf_rd_i",
    "qid",
    # Social media
    "share",
    "sharesource",
    "fbclid",
    "igshid",
    # Email tracking
    "mkt_tok",
    "trk",
    "trkid",
    # Session IDs
    "sessionid",
    "sid",
    "phpsessid",
    "jsessionid",
    # Other
    "_hsenc",
    "_hsmi",
    "mibextid",
}


def normalize_url(url: str, keep_fragments: bool = False) -> str:
    """
    Normalize URL for consistent comparison and storage.

    This function:
    - Lowercases the scheme and domain
    - Removes default ports (80 for HTTP, 443 for HTTPS)
    - Removes trailing slashes
    - Removes tracking parameters
    - Sorts remaining query parameters
    - Removes fragments (optional)

    Args:
        url: URL to normalize
        keep_fragments: Whether to keep URL fragments (default: False)

    Returns:
        Normalized URL string

    Example:
        >>> normalize_url("HTTPS://Example.COM/Path?utm_source=test&id=123")
        'https://example.com/Path?id=123'
    """
    try:
        # Basic normalization using url-normalize
        normalized = url_normalize(url)

        # Parse URL
        parsed = urlparse(normalized)

        # Remove tracking parameters
        if parsed.query:
            query_params = parse_qs(parsed.query, keep_blank_values=True)
            # Filter out tracking parameters
            cleaned_params = {
                k: v for k, v in query_params.items() if k.lower() not in TRACKING_PARAMS
            }
            # Sort and rebuild query string
            if cleaned_params:
                # Flatten list values and sort
                sorted_params = sorted(
                    [(k, v[0] if len(v) == 1 else v) for k, v in cleaned_params.items()]
                )
                new_query = urlencode(sorted_params, doseq=True)
            else:
                new_query = ""
        else:
            new_query = parsed.query

        # Remove fragment unless explicitly kept
        fragment = parsed.fragment if keep_fragments else ""

        # Rebuild URL
        normalized_url = urlunparse(
            (
                parsed.scheme.lower(),
                parsed.netloc.lower(),
                parsed.path,
                parsed.params,
                new_query,
                fragment,
            )
        )

        # Additional canonicalization using w3lib
        normalized_url = canonicalize_url(normalized_url, keep_fragments=keep_fragments)

        logger.debug(
            "URL normalized",
            extra={
                "original": url,
                "normalized": normalized_url,
            },
        )

        return normalized_url

    except Exception as e:
        logger.warning(
            "URL normalization failed, returning original",
            extra={
                "url": url,
                "error": str(e),
            },
        )
        return url


def clean_url_for_comparison(url: str) -> str:
    """
    Clean URL specifically for comparison/deduplication.

    More aggressive than normalize_url:
    - Removes all query parameters
    - Removes fragments
    - Removes trailing slashes
    - Lowercases entire URL

    Args:
        url: URL to clean

    Returns:
        Cleaned URL for comparison

    Example:
        >>> clean_url_for_comparison("https://example.com/product/123?color=red#reviews")
        'https://example.com/product/123'
    """
    try:
        # First normalize
        normalized = normalize_url(url, keep_fragments=False)

        # Parse and remove all query params
        parsed = urlparse(normalized)

        # Remove trailing slash from path
        path = parsed.path.rstrip("/") if parsed.path != "/" else parsed.path

        # Rebuild without query or fragment
        clean = urlunparse(
            (
                parsed.scheme.lower(),
                parsed.netloc.lower(),
                path,
                "",  # No params
                "",  # No query
                "",  # No fragment
            )
        )

        return clean

    except Exception as e:
        logger.warning(
            "URL cleaning failed, returning original",
            extra={
                "url": url,
                "error": str(e),
            },
        )
        return url


def extract_domain(url: str) -> Optional[str]:
    """
    Extract domain from URL.

    Args:
        url: URL to extract domain from

    Returns:
        Domain string or None if invalid

    Example:
        >>> extract_domain("https://www.example.com/path")
        'www.example.com'
    """
    try:
        parsed = urlparse(url)
        return parsed.netloc.lower() if parsed.netloc else None
    except Exception as e:
        logger.warning(
            "Domain extraction failed",
            extra={
                "url": url,
                "error": str(e),
            },
        )
        return None


def extract_base_domain(url: str) -> Optional[str]:
    """
    Extract base domain (without subdomain) from URL.

    Args:
        url: URL to extract base domain from

    Returns:
        Base domain or None if invalid

    Example:
        >>> extract_base_domain("https://shop.example.com/path")
        'example.com'
    """
    try:
        domain = extract_domain(url)
        if not domain:
            return None

        # Split domain parts
        parts = domain.split(".")

        # Handle special cases (e.g., co.uk, com.br)
        if len(parts) >= 3 and parts[-2] in {"co", "com", "gov", "org", "ac"}:
            return ".".join(parts[-3:])

        # Standard case: last two parts
        if len(parts) >= 2:
            return ".".join(parts[-2:])

        return domain

    except Exception as e:
        logger.warning(
            "Base domain extraction failed",
            extra={
                "url": url,
                "error": str(e),
            },
        )
        return None


def is_same_domain(url1: str, url2: str) -> bool:
    """
    Check if two URLs belong to the same base domain.

    Args:
        url1: First URL
        url2: Second URL

    Returns:
        True if same base domain

    Example:
        >>> is_same_domain("https://shop.example.com", "https://blog.example.com")
        True
    """
    domain1 = extract_base_domain(url1)
    domain2 = extract_base_domain(url2)
    return domain1 == domain2 if domain1 and domain2 else False


def add_tracking_param(param: str) -> None:
    """
    Add a custom tracking parameter to the removal list.

    Args:
        param: Parameter name to add

    Example:
        >>> add_tracking_param("my_custom_tracker")
    """
    TRACKING_PARAMS.add(param.lower())
    logger.debug(f"Added tracking parameter: {param}")


def is_valid_url(url: str) -> bool:
    """
    Check if URL is valid and well-formed.

    Args:
        url: URL to validate

    Returns:
        True if valid

    Example:
        >>> is_valid_url("https://example.com")
        True
        >>> is_valid_url("not a url")
        False
    """
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc]) and result.scheme in ["http", "https"]
    except Exception:
        return False


def ensure_scheme(url: str, default_scheme: str = "https") -> str:
    """
    Ensure URL has a scheme, add default if missing.

    Args:
        url: URL to check
        default_scheme: Scheme to add if missing (default: https)

    Returns:
        URL with scheme

    Example:
        >>> ensure_scheme("example.com/path")
        'https://example.com/path'
    """
    if not url.startswith(("http://", "https://")):
        return f"{default_scheme}://{url}"
    return url


# Export public API
__all__ = [
    "normalize_url",
    "clean_url_for_comparison",
    "extract_domain",
    "extract_base_domain",
    "is_same_domain",
    "add_tracking_param",
    "is_valid_url",
    "ensure_scheme",
]
