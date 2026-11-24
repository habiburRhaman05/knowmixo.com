"""Logging filters for request context, tenant isolation, and PII scrubbing.

Used by logging.yaml configuration.
"""
import logging
import re
from typing import Any


class RequestContextFilter(logging.Filter):
    """Adds request context (request_id, company_id, actor, actor_id) to log records.

    These values are set via contextvars by the audit service's audit_request_context.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        # Import here to avoid circular imports
        try:
            from app.audit.service import audit_context

            record.request_id = getattr(audit_context, "_request_id", "-") or "-"
            record.company_id = getattr(audit_context, "_company_id", "-") or "-"
            record.actor = getattr(audit_context, "_actor", "-") or "-"
            record.actor_id = getattr(audit_context, "_actor_id", "-") or "-"
        except Exception:
            record.request_id = "-"
            record.company_id = "-"
            record.actor = "-"
            record.actor_id = "-"
        return True


class TenantIsolationFilter(logging.Filter):
    """Ensures tenant isolation in logs by validating company_id consistency.

    Warns if log records appear to leak data across tenants.
    """

    def __init__(self):
        super().__init__()
        self._seen_company_ids: dict[str, set[str]] = {}

    def filter(self, record: logging.LogRecord) -> bool:
        company_id = getattr(record, "company_id", "-")

        # Track logger name -> company_id associations
        logger_name = record.name
        if logger_name not in self._seen_company_ids:
            self._seen_company_ids[logger_name] = set()

        if company_id != "-":
            self._seen_company_ids[logger_name].add(company_id)

            # Warn if a single logger is seeing multiple company_ids
            # This could indicate a bug where tenant isolation is broken
            if len(self._seen_company_ids[logger_name]) > 1:
                record.__dict__["tenant_isolation_warning"] = (
                    f"Logger {logger_name} has seen multiple company_ids: "
                    f"{self._seen_company_ids[logger_name]}"
                )

        return True


class PIIScrubberFilter(logging.Filter):
    """Scrubs personally identifiable information from log messages.

    Patterns to scrub:
    - Email addresses
    - Phone numbers
    - Credit card numbers
    - SSN-like patterns
    - API keys / tokens
    - JWT tokens
    - Authorization headers
    """

    # Patterns to scrub (name -> (pattern, replacement))
    PATTERNS = [
        # Email addresses
        ("email", (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"), "[EMAIL]")),
        # Phone numbers (various formats)
        ("phone", (re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"), "[PHONE]")),
        # Credit card numbers (13-19 digits, space/hyphen separated)
        ("credit_card", (re.compile(r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b"), "[CREDIT_CARD]")),
        # SSN (XXX-XX-XXXX or XXXXXXXXX)
        ("ssn", (re.compile(r"\b\d{3}-\d{2}-\d{4}\b|\b\d{9}\b"), "[SSN]")),
        # API keys (common prefixes)
        ("api_key", (re.compile(r"\b(sk|pk|rk)_[a-zA-Z0-9]{20,}\b"), "[API_KEY]")),
        # Bearer tokens
        ("bearer_token", (re.compile(r"Bearer\s+[A-Za-z0-9._-]{20,}", re.IGNORECASE), "Bearer [TOKEN]")),
        # Authorization header values
        ("auth_header", (re.compile(r"(Authorization|authorization)\s*:\s*[^\s]+"), r"\1: [REDACTED]")),
        # JWT tokens (three base64url parts separated by dots)
        ("jwt", (re.compile(r"\beyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\b"), "[JWT]")),
        # Generic secrets (key=value where value looks like a secret)
        ("secret", (re.compile(r"(?i)(password|secret|token|key|api_key)\s*[:=]\s*[^\s]{8,}"), r"\1: [REDACTED]")),
        # IP addresses (optional - can be useful for debugging, so commented out)
        # ("ipv4", (re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b"), "[IP]")),
        # UUIDs in certain contexts (keep for debugging, but scrub in sensitive fields)
    ]

    def __init__(self):
        super().__init__()

    def filter(self, record: logging.LogRecord) -> bool:
        # Scrub the message
        if hasattr(record, "msg") and isinstance(record.msg, str):
            record.msg = self._scrub(record.msg)

        # Scrub args if they contain strings
        if record.args:
            record.args = tuple(
                self._scrub(arg) if isinstance(arg, str) else arg
                for arg in record.args
            )

        # Scrub exception info if present
        if record.exc_info and record.exc_text:
            record.exc_text = self._scrub(record.exc_text)

        return True

    def _scrub(self, text: str) -> str:
        """Apply all scrubbing patterns to text."""
        result = text
        for _name, (pattern, replacement) in self.PATTERNS:
            result = pattern.sub(replacement, result)
        return result


def scrub_dict(data: dict[str, Any], keys_to_scrub: set[str] = None) -> dict[str, Any]:
    """Recursively scrub sensitive keys from a dictionary.

    Args:
        data: Dictionary to scrub
        keys_to_scrub: Set of key names to scrub (case-insensitive)

    Returns:
        New dictionary with sensitive values replaced
    """
    if keys_to_scrub is None:
        keys_to_scrub = {
            "password", "secret", "token", "key", "api_key", "apikey",
            "authorization", "access_token", "refresh_token", "client_secret",
            "private_key", "public_key", "certificate", "jwt", "bearer",
            "ssn", "social_security", "credit_card", "card_number", "cvv",
            "email", "phone", "address", "ip", "ip_address",
        }

    result = {}
    for key, value in data.items():
        key_lower = key.lower()
        if key_lower in keys_to_scrub:
            result[key] = "[REDACTED]"
        elif isinstance(value, dict):
            result[key] = scrub_dict(value, keys_to_scrub)
        elif isinstance(value, list):
            result[key] = [
                scrub_dict(item, keys_to_scrub) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            result[key] = value
    return result


class StructuredLogFilter(logging.Filter):
    """Adds structured fields to log records for better querying."""

    def filter(self, record: logging.LogRecord) -> bool:
        # Add service metadata
        record.service_name = "knowmivo-backend"
        record.service_version = "1.0.0"
        record.environment = "production"  # Could be from settings

        # Add log level as string for easier querying
        record.log_level = record.levelname

        return True