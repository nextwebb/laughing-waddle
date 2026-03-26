import asyncio
import random
import time
from typing import Any, Callable, Coroutine

from app.models import RetryAttempt

RETRYABLE_EXCEPTIONS = (TimeoutError, ConnectionError, ConnectionRefusedError)


async def retry_with_backoff(
    coro_factory: Callable[[], Coroutine],
    *,
    max_retries: int = 3,
    base_delay: float = 0.5,
    max_delay: float = 8.0,
    timeout_per_attempt: float = 5.0,
) -> tuple[Any, list[RetryAttempt]]:
    """Run a coroutine with retries. coro_factory must return a fresh coroutine each call —
    you can't re-await an exhausted coroutine."""
    attempts: list[RetryAttempt] = []
    pending_delay = 0.0

    for attempt in range(max_retries + 1):
        # Sleep the backoff delay computed from the previous failed attempt
        if pending_delay > 0:
            await asyncio.sleep(pending_delay)
        delay_this_attempt = pending_delay
        pending_delay = 0.0

        start = time.monotonic()
        try:
            result = await asyncio.wait_for(
                coro_factory(), timeout=timeout_per_attempt
            )
            elapsed = (time.monotonic() - start) * 1000
            attempts.append(
                RetryAttempt(
                    attempt=attempt,
                    delay_applied=round(delay_this_attempt, 4),
                    error=None,
                    latency_ms=round(elapsed, 2),
                )
            )
            return result, attempts

        except RETRYABLE_EXCEPTIONS as exc:
            elapsed = (time.monotonic() - start) * 1000
            attempts.append(
                RetryAttempt(
                    attempt=attempt,
                    delay_applied=round(delay_this_attempt, 4),
                    error=f"{type(exc).__name__}: {exc}",
                    latency_ms=round(elapsed, 2),
                )
            )
            if attempt == max_retries:
                exc.attempts = attempts  # type: ignore[attr-defined]
                raise

            # Full jitter: decorrelates concurrent retry storms
            ceiling = min(max_delay, base_delay * (2 ** attempt))
            pending_delay = random.uniform(0, ceiling)

        except Exception as exc:
            elapsed = (time.monotonic() - start) * 1000
            attempts.append(
                RetryAttempt(
                    attempt=attempt,
                    delay_applied=round(delay_this_attempt, 4),
                    error=f"{type(exc).__name__}: {exc}",
                    latency_ms=round(elapsed, 2),
                )
            )
            exc.attempts = attempts  # type: ignore[attr-defined]
            raise
