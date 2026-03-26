import asyncio

# Tracks call count per (request_id, handler) for transient scenario.
# Module-level is fine — single-process, in-memory, cooperative multitasking.
_attempt_tracker: dict[str, int] = {}

TRANSIENT_FAIL_COUNT = 2


async def _succeed():
    await asyncio.sleep(0.05)
    return "processed successfully"


async def _timeout():
    raise TimeoutError("simulated timeout")


async def _transient(request_id: str, handler_name: str):
    key = f"{request_id}:{handler_name}"
    _attempt_tracker[key] = _attempt_tracker.get(key, 0) + 1
    if _attempt_tracker[key] <= TRANSIENT_FAIL_COUNT:
        raise ConnectionError(
            f"transient failure (attempt {_attempt_tracker[key]})"
        )
    return "recovered after transient failures"


async def _hard_fail():
    raise ValueError("permanent failure — non-retryable")


_SCENARIOS = {
    "ok": lambda rid, name: _succeed(),
    "timeout": lambda rid, name: _timeout(),
    "transient_fail_then_ok": _transient,
    "hard_fail": lambda rid, name: _hard_fail(),
}


async def _dispatch(scenario: str, request_id: str, handler_name: str) -> str:
    fn = _SCENARIOS.get(scenario)
    if fn is None:
        raise ValueError(f"unknown scenario: {scenario}")
    return await fn(request_id, handler_name)


async def primary_handler(payload: dict, request_id: str) -> str:
    scenario = payload.get("primary_scenario") or payload.get("scenario", "ok")
    return await _dispatch(scenario, request_id, "primary")


async def optional_handler(payload: dict, request_id: str) -> str:
    scenario = payload.get("optional_scenario") or payload.get("scenario", "ok")
    return await _dispatch(scenario, request_id, "optional")
