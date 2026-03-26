from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models import ProcessingRequest


def _empty_handler_metrics() -> dict:
    return {"success": 0, "failure": 0, "total_latency_ms": 0.0, "count": 0}


_state: dict = {
    "processed": 0,
    "succeeded": 0,
    "failed": 0,
    "degraded": 0,
    "handlers": {
        "primary": _empty_handler_metrics(),
        "optional": _empty_handler_metrics(),
    },
}


def record(req: ProcessingRequest) -> None:
    _state["processed"] += 1

    if req.status.value == "completed":
        _state["succeeded"] += 1
    else:
        _state["failed"] += 1

    if req.degraded:
        _state["degraded"] += 1

    for name, result in [("primary", req.primary_result), ("optional", req.optional_result)]:
        if result is None:
            continue
        h = _state["handlers"][name]
        h["count"] += 1
        h["total_latency_ms"] += result.latency_ms
        if result.status == "success":
            h["success"] += 1
        else:
            h["failure"] += 1


def snapshot() -> dict:
    out = {
        "processed": _state["processed"],
        "succeeded": _state["succeeded"],
        "failed": _state["failed"],
        "degraded": _state["degraded"],
        "handlers": {},
    }
    for name in ("primary", "optional"):
        h = _state["handlers"][name]
        count = h["count"]
        out["handlers"][name] = {
            **h,
            "avg_latency_ms": round(h["total_latency_ms"] / count, 2) if count else 0,
        }
    return out


def reset() -> None:
    """For test isolation only."""
    _state["processed"] = 0
    _state["succeeded"] = 0
    _state["failed"] = 0
    _state["degraded"] = 0
    for name in ("primary", "optional"):
        _state["handlers"][name] = _empty_handler_metrics()
