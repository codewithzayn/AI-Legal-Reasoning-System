"""
Retry with exponential backoff for OpenAI and Cohere API calls.
Handles transient failures: rate limits, timeouts, connection errors.
"""

import asyncio
import functools
import time

from src.config.logging_config import setup_logger

logger = setup_logger(__name__)

# Retry config
DEFAULT_RETRIES = 3
DEFAULT_INITIAL_DELAY = 1.0
DEFAULT_MAX_DELAY = 30.0
DEFAULT_BACKOFF = 2.0

# Exception names that indicate transient (retryable) errors
RETRYABLE_OPENAI = ("RateLimitError", "APIConnectionError", "APITimeoutError")
RETRYABLE_COHERE = (
    "RateLimitError",
    "CohereConnectionError",
    "CohereTimeoutError",
    "CohereAPIError",
    "CohereError",
)


def _is_retryable(exc: BaseException) -> bool:
    """Check if exception is retryable (rate limit, timeout, connection)."""
    name = type(exc).__name__
    if name in RETRYABLE_OPENAI or name in RETRYABLE_COHERE:
        return True
    msg = str(exc).lower()
    return "429" in msg or "rate" in msg or "timeout" in msg or "connection" in msg or "503" in msg


def _sync_retry_impl(
    fn,
    *args,
    retries: int = DEFAULT_RETRIES,
    initial_delay: float = DEFAULT_INITIAL_DELAY,
    max_delay: float = DEFAULT_MAX_DELAY,
    backoff: float = DEFAULT_BACKOFF,
    **kwargs,
):
    """Synchronous retry with exponential backoff."""
    last_exc = None
    delay = initial_delay
    for attempt in range(retries + 1):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            last_exc = e
            if attempt < retries and _is_retryable(e):
                logger.warning("Retry %s/%s after %s: %s", attempt + 1, retries, type(e).__name__, e)
                time.sleep(delay)
                delay = min(delay * backoff, max_delay)
            else:
                raise
    raise last_exc


async def _async_retry_impl(
    fn,
    *args,
    retries: int = DEFAULT_RETRIES,
    initial_delay: float = DEFAULT_INITIAL_DELAY,
    max_delay: float = DEFAULT_MAX_DELAY,
    backoff: float = DEFAULT_BACKOFF,
    **kwargs,
):
    """Async retry with exponential backoff."""
    last_exc = None
    delay = initial_delay
    for attempt in range(retries + 1):
        try:
            return await fn(*args, **kwargs)
        except Exception as e:
            last_exc = e
            if attempt < retries and _is_retryable(e):
                logger.warning("Retry %s/%s after %s: %s", attempt + 1, retries, type(e).__name__, e)
                await asyncio.sleep(delay)
                delay = min(delay * backoff, max_delay)
            else:
                raise
    raise last_exc


def with_retry(
    retries: int = DEFAULT_RETRIES,
    initial_delay: float = DEFAULT_INITIAL_DELAY,
    max_delay: float = DEFAULT_MAX_DELAY,
    backoff: float = DEFAULT_BACKOFF,
):
    """Decorator for sync functions: retry with exponential backoff."""

    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            return _sync_retry_impl(
                fn, *args, retries=retries, initial_delay=initial_delay, max_delay=max_delay, backoff=backoff, **kwargs
            )

        return wrapper

    return decorator


async def retry_async(coro_fn):
    """
    Retry an async call. Usage: await retry_async(lambda: client.ainvoke(...))
    """
    return await _async_retry_impl(coro_fn)


def with_async_retry(
    retries: int = DEFAULT_RETRIES,
    initial_delay: float = DEFAULT_INITIAL_DELAY,
    max_delay: float = DEFAULT_MAX_DELAY,
    backoff: float = DEFAULT_BACKOFF,
):
    """Decorator for async functions: retry with exponential backoff."""

    def decorator(fn):
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            return await _async_retry_impl(
                fn, *args, retries=retries, initial_delay=initial_delay, max_delay=max_delay, backoff=backoff, **kwargs
            )

        return wrapper

    return decorator
