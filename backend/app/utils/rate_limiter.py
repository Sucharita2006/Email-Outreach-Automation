"""
Async Rate Limiter — Token Bucket + Semaphore for API calls.
Prevents exceeding OpenRouter / Hunter / Serper rate limits on batch operations.
"""
import asyncio
import time
from typing import Optional


class AsyncSemaphoreRateLimiter:
    """
    Combines asyncio.Semaphore (concurrent call limit) with a minimum
    interval between calls (requests-per-second limit).

    Usage:
        limiter = AsyncSemaphoreRateLimiter(max_concurrent=10, min_interval=0.1)
        async with limiter:
            result = await call_api(...)
    """

    def __init__(self, max_concurrent: int = 10, min_interval: float = 0.0):
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._min_interval = min_interval
        self._last_call_time: float = 0.0
        self._lock = asyncio.Lock()

    async def __aenter__(self):
        await self._semaphore.acquire()
        if self._min_interval > 0:
            async with self._lock:
                now = time.monotonic()
                wait = self._min_interval - (now - self._last_call_time)
                if wait > 0:
                    await asyncio.sleep(wait)
                self._last_call_time = time.monotonic()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        self._semaphore.release()


async def with_exponential_backoff(
    coro_fn,
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
):
    """
    Execute an async coroutine function with exponential backoff on failure.
    Retries on any exception (typically 429 rate limit or 5xx errors).

    Usage:
        result = await with_exponential_backoff(lambda: call_openrouter(prompt))
    """
    for attempt in range(max_retries):
        try:
            return await coro_fn()
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            delay = min(base_delay * (2 ** attempt), max_delay)
            await asyncio.sleep(delay)


class RateLimiter(AsyncSemaphoreRateLimiter):
    """
    Alias for AsyncSemaphoreRateLimiter with a friendlier constructor.
    Usage: RateLimiter(concurrency=5, calls_per_second=2.0)
    """
    def __init__(self, concurrency: int = 10, calls_per_second: float = 0.0):
        min_interval = (1.0 / calls_per_second) if calls_per_second > 0 else 0.0
        super().__init__(max_concurrent=concurrency, min_interval=min_interval)

