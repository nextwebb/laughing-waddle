# Design Notes

## Concurrency: asyncio

In-memory service, two handlers, run them in parallel. No queue backpressure, no distributed workers, no persistent task state. asyncio does this with zero external dependencies — `asyncio.gather` on two coroutines and we're done.

Celery would add a broker for no benefit here. It solves a different problem.

## Retry and backoff

Exponential backoff with full jitter.

```
ceiling = min(max_delay, base_delay * 2^attempt)
delay   = uniform(0, ceiling)
```

Full jitter randomizes over the entire range. Without it, concurrent failures retry in lockstep — a thundering herd. Full jitter decorrelates them.

Max delay cap prevents runaway waits at high attempt counts. Base 0.5s at attempt 10 is 512s uncapped. I cap at 4s.

Retry whitelist: `TimeoutError`, `ConnectionError`, `ConnectionRefusedError`. Transient failures where a retry might work. Everything else fails immediately — retrying a `ValueError` just repeats the same permanent failure.

## Orchestration

`_run_handler` never raises. It always returns a `HandlerResult` with `"success"` or `"error"`.

Why: if a handler fails after three retries, those attempts — delay, error, latency per try — need to appear in the GET response. Letting exceptions bubble through `gather` loses that history.

This makes `process_request` three branches:
- Primary error → request fails
- Primary OK, optional error → completed, degraded, with reason
- Both OK → completed

## Timeouts

Two layers.

**Per-attempt**: `asyncio.wait_for` on each handler call. Slow attempt gets cancelled, raises `TimeoutError`, triggers retry.

**Per-handler global cap**: wraps the entire retry loop. Prevents the optional handler from blocking the response indefinitely — even if individual attempts are within timeout, stacked retries with backoff add up.

## POST returns 202

The spec says POST returns `request_id` and `initial status`. "Initial" implies the status changes later. Processing is async — POST fires the background task, returns immediately. Client polls GET.

Synchronous POST was considered. Rejected because it blocks the caller for the duration of retries + backoff, and doesn't demonstrate concurrency at the API level.

## Per-handler scenario overrides

A single `scenario` field applies to both handlers. Problem: you can't test the degraded path — either both succeed or both fail.

Fix: `primary_scenario` / `optional_scenario` override the shared field per handler. Three lines of `dict.get` fallback. Without this, graceful degradation isn't demonstrable.

## What's missing (deliberately)

- **Circuit breaker.** Retries are bounded by `max_retries` but not adaptive. Sustained downstream failure still burns through all attempts per request.
- **Persistence.** Module-level dict. Process restart wipes everything. Production needs Redis or Postgres with transactional state transitions.
- **Structured logging.** Observability is through the health endpoint and per-request attempt history. Production needs correlation IDs and structured logs.
- **Multi-process safety.** The in-memory dict is safe under asyncio's cooperative model — one thread, one event loop, no races without yielding in a critical section. Multiple gunicorn workers break this assumption. Needs external state or single-worker architecture.
