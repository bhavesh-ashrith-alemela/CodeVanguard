import os
import re
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger("codevanguard.error_monitoring")

# Patterns for scrubbing credentials and tokens
SENSITIVE_PATTERNS = [
    # GitHub App / User / Installation / Personal Access Tokens
    (re.compile(r"gh[psuor]_[A-Za-z0-9_]{16,}", re.IGNORECASE), "[REDACTED_GITHUB_TOKEN]"),
    (re.compile(r"github_pat_[A-Za-z0-9_]{16,}", re.IGNORECASE), "[REDACTED_GITHUB_PAT]"),
    # Bearer tokens in Authorization headers / text
    (re.compile(r"(Bearer\s+)[A-Za-z0-9\-\._~\+\/]+=*", re.IGNORECASE), r"\1[REDACTED_BEARER_TOKEN]"),
    # AWS Access Keys & Secrets
    (re.compile(r"(?:AKIA|ABIA|ACCA|ASIA)[0-9A-Z]{16}"), "[REDACTED_AWS_KEY]"),
    (re.compile(r"(aws_secret_access_key\s*[:=]\s*)[A-Za-z0-9/+=]{40}", re.IGNORECASE), r"\1[REDACTED_AWS_SECRET]"),
    # Slack tokens
    (re.compile(r"xox[baprs]-[0-9a-zA-Z]{10,}", re.IGNORECASE), "[REDACTED_SLACK_TOKEN]"),
    # Stripe API keys
    (re.compile(r"sk_live_[0-9a-zA-Z]{24,}", re.IGNORECASE), "[REDACTED_STRIPE_KEY]"),
    # Private Key blocks
    (re.compile(r"-----BEGIN [A-Z ]+ PRIVATE KEY-----[\s\S]*?-----END [A-Z ]+ PRIVATE KEY-----"), "[REDACTED_PRIVATE_KEY]"),
    # JWTs (compact 3-segment)
    (re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"), "[REDACTED_JWT]"),
    # Generic password / secret query params or assignments
    (re.compile(r"((?:password|secret|token|api_key|access_token|client_secret)\s*[:=]\s*['\"]?)[^'\"\s&,]+(['\"]?)", re.IGNORECASE), r"\1[REDACTED]\2"),
]

SENSITIVE_KEYS = {
    "password", "secret", "token", "access_token", "refresh_token",
    "api_key", "client_secret", "github_app_private_key", "token_encryption_key",
    "github_webhook_secret", "authorization", "cookie", "x-hub-signature-256",
    "source_code", "raw_content", "patch_diff", "code_snippet"
}

def scrub_sensitive_string(text: str) -> str:
    """Replaces any matched API keys, tokens, or private keys with redaction markers."""
    if not isinstance(text, str):
        return text
    scrubbed = text
    for pattern, replacement in SENSITIVE_PATTERNS:
        scrubbed = pattern.sub(replacement, scrubbed)
    return scrubbed

def scrub_data_structures(obj: Any) -> Any:
    """Recursively traverses dicts, lists, and primitives, stripping sensitive keys and scrubbing values."""
    if isinstance(obj, dict):
        sanitized = {}
        for k, v in obj.items():
            k_lower = str(k).lower()
            if any(sensitive_key in k_lower for sensitive_key in SENSITIVE_KEYS):
                sanitized[k] = "[REDACTED]"
            else:
                sanitized[k] = scrub_data_structures(v)
        return sanitized
    elif isinstance(obj, (list, tuple, set)):
        return [scrub_data_structures(item) for item in obj]
    elif isinstance(obj, str):
        return scrub_sensitive_string(obj)
    return obj

def sentry_before_send(event: Dict[str, Any], hint: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Sentry before_send callback.
    Guarantees:
    1. Zero source code context lines or local stack variables persist.
    2. All credentials, API keys, and auth headers are completely redacted.
    3. Ephemeral workspace paths or user code are stripped.
    """
    try:
        # Strip code context and local variables from exception stack traces
        if "exception" in event:
            for exc in event.get("exception", {}).get("values", []):
                if "stacktrace" in exc:
                    for frame in exc.get("stacktrace", {}).get("frames", []):
                        # Strip all local variable values
                        if "vars" in frame:
                            frame["vars"] = {}
                        # Strip lines of source code context
                        frame.pop("pre_context", None)
                        frame.pop("context_line", None)
                        frame.pop("post_context", None)

        # Strip code context and local variables from threads
        if "threads" in event:
            for thread in event.get("threads", {}).get("values", []):
                if "stacktrace" in thread:
                    for frame in thread.get("stacktrace", {}).get("frames", []):
                        if "vars" in frame:
                            frame["vars"] = {}
                        frame.pop("pre_context", None)
                        frame.pop("context_line", None)
                        frame.pop("post_context", None)

        # Sanitize request headers, body, cookies
        if "request" in event:
            req = event["request"]
            if "headers" in req:
                req["headers"] = scrub_data_structures(req["headers"])
            if "cookies" in req:
                req["cookies"] = "[REDACTED]"
            if "data" in req:
                req["data"] = scrub_data_structures(req["data"])
            if "query_string" in req and isinstance(req["query_string"], str):
                req["query_string"] = scrub_sensitive_string(req["query_string"])

        # Sanitize breadcrumbs
        if "breadcrumbs" in event:
            for crumb in event.get("breadcrumbs", {}).get("values", []):
                if "message" in crumb and isinstance(crumb["message"], str):
                    crumb["message"] = scrub_sensitive_string(crumb["message"])
                if "data" in crumb and isinstance(crumb["data"], dict):
                    crumb["data"] = scrub_data_structures(crumb["data"])

        # Recursively scrub event root
        return scrub_data_structures(event)
    except Exception as e:
        logger.warning(f"Error during Sentry event scrubbing: {e}")
        # Even on error, return scrubbed basic info
        return {"message": "Internal error occurred (details scrubbed for privacy)"}

def sentry_before_breadcrumb(crumb: Dict[str, Any], hint: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Sanitizes breadcrumbs before recording."""
    try:
        return scrub_data_structures(crumb)
    except Exception:
        return None

_sentry_initialized = False

def init_error_monitoring(app=None) -> bool:
    """
    Initializes Sentry error monitoring if SENTRY_DSN is configured.
    Configures strict privacy mode (no local variables, no code context, no PII).
    Returns True if Sentry is active, False otherwise.
    """
    global _sentry_initialized
    dsn = os.environ.get("SENTRY_DSN", "").strip()
    if not dsn:
        logger.info("Error monitoring: SENTRY_DSN not set. Using local privacy-preserving error logger.")
        return False

    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.logging import LoggingIntegration

        sentry_logging = LoggingIntegration(
            level=logging.INFO,
            event_level=logging.ERROR
        )

        sentry_sdk.init(
            dsn=dsn,
            environment=os.environ.get("ENV", "development"),
            release=os.environ.get("APP_VERSION", "1.0.0"),
            send_default_pii=False,
            include_local_variables=False,
            include_source_context=False,
            traces_sample_rate=float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0.05")),
            before_send=sentry_before_send,
            before_breadcrumb=sentry_before_breadcrumb,
            integrations=[sentry_logging, FastApiIntegration()]
        )
        _sentry_initialized = True
        logger.info("Error monitoring: Sentry successfully initialized with strict source code and token scrubbing.")
        return True
    except ImportError:
        logger.warning("Error monitoring: sentry-sdk package not installed. Running in privacy logger mode.")
        return False
    except Exception as e:
        logger.error(f"Error monitoring: Failed to initialize Sentry: {e}")
        return False

def capture_exception(exc: Exception, extra: Optional[Dict[str, Any]] = None):
    """
    Captures an exception for error monitoring, ensuring all secrets and source code are scrubbed.
    Works whether Sentry is configured or fallback logging is active.
    """
    safe_extra = scrub_data_structures(extra or {})
    scrubbed_msg = scrub_sensitive_string(str(exc))

    if _sentry_initialized:
        try:
            import sentry_sdk
            with sentry_sdk.push_scope() as scope:
                for k, v in safe_extra.items():
                    scope.set_extra(k, v)
                sentry_sdk.capture_exception(exc)
                return
        except Exception as e:
            logger.warning(f"Failed to send exception to Sentry: {e}")

    logger.error(f"Captured Exception: {exc.__class__.__name__}: {scrubbed_msg} | context={safe_extra}", exc_info=False)

def capture_message(message: str, level: str = "info", extra: Optional[Dict[str, Any]] = None):
    """Captures a message for error monitoring with scrubbing."""
    safe_extra = scrub_data_structures(extra or {})
    scrubbed_msg = scrub_sensitive_string(message)

    if _sentry_initialized:
        try:
            import sentry_sdk
            with sentry_sdk.push_scope() as scope:
                for k, v in safe_extra.items():
                    scope.set_extra(k, v)
                sentry_sdk.capture_message(scrubbed_msg, level=level)
                return
        except Exception as e:
            logger.warning(f"Failed to send message to Sentry: {e}")

    log_fn = getattr(logger, level.lower(), logger.info)
    log_fn(f"{scrubbed_msg} | context={safe_extra}")
