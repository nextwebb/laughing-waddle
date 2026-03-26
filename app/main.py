import asyncio
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException

from app import metrics
from app.handlers import optional_handler, primary_handler
from app.models import HandlerResult, ProcessingRequest, RequestStatus
from app.retry import retry_with_backoff

app = FastAPI(title="Resilient Processing Pipeline")

# In-memory store. Single-process, single event loop — no lock needed.
_requests: dict[str, ProcessingRequest] = {}

# Retry / timeout defaults — tuned low for fast feedback during demos
MAX_RETRIES = 3
BASE_DELAY = 0.3
MAX_DELAY = 4.0
TIMEOUT_PER_ATTEMPT = 3.0
MAX_HANDLER_DURATION = 15.0


async def _run_handler(handler, payload: dict, request_id: str, name: str) -> HandlerResult:
    """Always returns a HandlerResult — never raises. Keeps retry attempts visible on failure."""
    try:
        result, attempts = await asyncio.wait_for(
            retry_with_backoff(
                lambda: handler(payload, request_id),
                max_retries=MAX_RETRIES,
                base_delay=BASE_DELAY,
                max_delay=MAX_DELAY,
                timeout_per_attempt=TIMEOUT_PER_ATTEMPT,
            ),
            timeout=MAX_HANDLER_DURATION,
        )
        total_latency = sum(a.latency_ms for a in attempts)
        return HandlerResult(
            status="success",
            result=result,
            latency_ms=round(total_latency, 2),
            attempts=attempts,
        )
    except Exception as exc:
        attempts = getattr(exc, "attempts", [])
        total_latency = sum(a.latency_ms for a in attempts)
        return HandlerResult(
            status="error",
            error=f"{type(exc).__name__}: {exc}",
            latency_ms=round(total_latency, 2),
            attempts=attempts,
        )


async def process_request(req: ProcessingRequest) -> None:
    req.status = RequestStatus.RUNNING
    req.started_at = datetime.now(timezone.utc)
    _requests[req.id] = req

    primary_task = asyncio.create_task(
        _run_handler(primary_handler, req.payload, req.id, "primary")
    )
    optional_task = asyncio.create_task(
        _run_handler(optional_handler, req.payload, req.id, "optional")
    )

    primary_out, optional_out = await asyncio.gather(primary_task, optional_task)

    req.primary_result = primary_out
    req.optional_result = optional_out

    if primary_out.status == "error":
        req.status = RequestStatus.FAILED
    elif optional_out.status == "error":
        req.status = RequestStatus.COMPLETED
        req.degraded = True
        req.degradation_reason = f"optional_handler failed: {optional_out.error}"
    else:
        req.status = RequestStatus.COMPLETED

    req.finished_at = datetime.now(timezone.utc)
    _requests[req.id] = req
    metrics.record(req)


@app.post("/requests", status_code=202)
async def create_request(payload: dict):
    req = ProcessingRequest(payload=payload)
    _requests[req.id] = req
    asyncio.create_task(process_request(req))
    return {"request_id": req.id, "status": req.status.value}


@app.get("/requests/{request_id}")
async def get_request(request_id: str):
    req = _requests.get(request_id)
    if not req:
        raise HTTPException(status_code=404, detail=f"request {request_id} not found")
    return req.model_dump(mode="json")


@app.get("/health")
async def health():
    return metrics.snapshot()
