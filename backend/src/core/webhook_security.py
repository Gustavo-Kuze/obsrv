"""
Webhook security utilities for HMAC signature generation and verification.

Implements Stripe-style webhook signatures with replay protection.
"""

import hashlib
import hmac
import time
from typing import Optional

from backend.src.core.logging import get_logger

logger = get_logger(__name__)


class WebhookSecurity:
    """
    Webhook security service for HMAC signature generation and verification.

    Implements signature format: t={unix_timestamp},v1={hmac_signature}
    - Replay protection with 5-minute tolerance window
    - HMAC-SHA256 signatures
    - Constant-time comparison to prevent timing attacks
    """

    # Replay protection window (seconds)
    TOLERANCE_WINDOW = 300  # 5 minutes

    def generate_signature(
        self,
        payload: str,
        webhook_secret: str,
        timestamp: Optional[int] = None,
    ) -> tuple[str, int]:
        """
        Generate HMAC-SHA256 signature for webhook payload.

        Args:
            payload: JSON payload string
            webhook_secret: Client's webhook secret
            timestamp: Unix timestamp (defaults to current time)

        Returns:
            Tuple of (signature_header, timestamp)
            signature_header format: "t={timestamp},v1={signature}"

        Example:
            >>> signature, ts = generate_signature('{"event":"test"}', 'secret123')
            >>> signature
            't=1699000000,v1=a1b2c3d4e5f6...'
        """
        # Use current time if not provided
        if timestamp is None:
            timestamp = int(time.time())

        # Create signed payload: {timestamp}.{payload}
        signed_payload = f"{timestamp}.{payload}"

        # Generate HMAC-SHA256 signature
        signature = hmac.new(
            key=webhook_secret.encode("utf-8"),
            msg=signed_payload.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).hexdigest()

        # Format signature header
        signature_header = f"t={timestamp},v1={signature}"

        logger.debug(
            "Generated webhook signature",
            extra={
                "timestamp": timestamp,
                "payload_length": len(payload),
            },
        )

        return signature_header, timestamp

    def verify_signature(
        self,
        payload: str,
        signature_header: str,
        webhook_secret: str,
    ) -> tuple[bool, Optional[str]]:
        """
        Verify HMAC-SHA256 signature for webhook payload.

        Args:
            payload: JSON payload string (raw request body)
            signature_header: Signature header value
            webhook_secret: Client's webhook secret

        Returns:
            Tuple of (is_valid, error_message)
            is_valid: True if signature is valid
            error_message: Error description if invalid, None if valid

        Example:
            >>> is_valid, error = verify_signature(
            ...     '{"event":"test"}',
            ...     't=1699000000,v1=a1b2c3d4...',
            ...     'secret123'
            ... )
            >>> is_valid
            True
        """
        # Parse signature header
        try:
            parts = dict(item.split("=", 1) for item in signature_header.split(","))
            timestamp_str = parts.get("t")
            received_signature = parts.get("v1")

            if not timestamp_str or not received_signature:
                return False, "Malformed signature header - missing t or v1"

            timestamp = int(timestamp_str)

        except (KeyError, ValueError) as e:
            logger.warning(
                "Failed to parse webhook signature header",
                extra={"error": str(e)},
            )
            return False, f"Malformed signature header: {str(e)}"

        # Check timestamp freshness (replay protection)
        current_time = int(time.time())
        time_diff = abs(current_time - timestamp)

        if time_diff > self.TOLERANCE_WINDOW:
            logger.warning(
                "Webhook signature timestamp too old",
                extra={
                    "timestamp": timestamp,
                    "current_time": current_time,
                    "diff_seconds": time_diff,
                },
            )
            return (
                False,
                f"Signature timestamp too old (diff: {time_diff}s, max: {self.TOLERANCE_WINDOW}s)",
            )

        # Compute expected signature
        signed_payload = f"{timestamp}.{payload}"
        expected_signature = hmac.new(
            key=webhook_secret.encode("utf-8"),
            msg=signed_payload.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).hexdigest()

        # Constant-time comparison to prevent timing attacks
        is_valid = hmac.compare_digest(expected_signature, received_signature)

        if not is_valid:
            logger.warning(
                "Webhook signature verification failed",
                extra={"timestamp": timestamp},
            )
            return False, "Signature verification failed"

        logger.debug(
            "Webhook signature verified successfully",
            extra={"timestamp": timestamp},
        )

        return True, None

    def verify_signature_with_rotation(
        self,
        payload: str,
        signature_header: str,
        current_secret: str,
        previous_secret: Optional[str] = None,
    ) -> tuple[bool, Optional[str]]:
        """
        Verify signature with support for secret rotation.

        During secret rotation grace period (1 hour), both current and
        previous secrets are accepted.

        Args:
            payload: JSON payload string
            signature_header: Signature header value
            current_secret: Current webhook secret
            previous_secret: Previous secret (during rotation)

        Returns:
            Tuple of (is_valid, error_message)
        """
        # Try current secret first
        is_valid, error = self.verify_signature(payload, signature_header, current_secret)

        if is_valid:
            return True, None

        # If current secret fails and previous secret exists, try previous
        if previous_secret:
            logger.debug("Trying previous webhook secret during rotation grace period")
            is_valid, error = self.verify_signature(payload, signature_header, previous_secret)

            if is_valid:
                logger.info("Webhook verified with previous secret during rotation")
                return True, None

        return False, error


# Singleton instance
webhook_security = WebhookSecurity()

# Export
__all__ = ["WebhookSecurity", "webhook_security"]
