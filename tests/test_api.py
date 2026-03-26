import asyncio

import pytest


async def _poll_until_done(client, request_id, timeout=10.0, interval=0.2):
    """Poll GET /requests/{id} until status is terminal or timeout."""
    elapsed = 0.0
    while elapsed < timeout:
        resp = await client.get(f"/requests/{request_id}")
        data = resp.json()
        if data["status"] in ("completed", "failed"):
            return data
        await asyncio.sleep(interval)
        elapsed += interval
    raise TimeoutError(f"request {request_id} did not finish within {timeout}s")


@pytest.mark.asyncio
async def test_both_handlers_ok_returns_completed(client):
    resp = await client.post("/requests", json={"scenario": "ok"})
    assert resp.status_code == 202
    request_id = resp.json()["request_id"]

    data = await _poll_until_done(client, request_id)

    assert data["status"] == "completed"
    assert data["degraded"] is False
    assert data["primary_result"]["status"] == "success"
    assert data["optional_result"]["status"] == "success"


@pytest.mark.asyncio
async def test_optional_timeout_returns_degraded(client):
    resp = await client.post("/requests", json={
        "primary_scenario": "ok",
        "optional_scenario": "timeout",
    })
    request_id = resp.json()["request_id"]

    data = await _poll_until_done(client, request_id)

    assert data["status"] == "completed"
    assert data["degraded"] is True
    assert "optional_handler failed" in data["degradation_reason"]
    assert data["primary_result"]["status"] == "success"


@pytest.mark.asyncio
async def test_primary_hard_fail_fails_request(client):
    resp = await client.post("/requests", json={
        "primary_scenario": "hard_fail",
        "optional_scenario": "ok",
    })
    request_id = resp.json()["request_id"]

    data = await _poll_until_done(client, request_id)

    assert data["status"] == "failed"
    assert data["primary_result"]["error"] is not None


@pytest.mark.asyncio
async def test_transient_failure_retries_then_succeeds(client):
    resp = await client.post("/requests", json={"scenario": "transient_fail_then_ok"})
    request_id = resp.json()["request_id"]

    data = await _poll_until_done(client, request_id, timeout=20.0)

    assert data["status"] == "completed"
    primary_attempts = data["primary_result"]["attempts"]
    assert len(primary_attempts) > 1
    assert primary_attempts[0]["error"] is not None
    assert primary_attempts[-1]["error"] is None


@pytest.mark.asyncio
async def test_health_reflects_processed_requests(client):
    resp = await client.post("/requests", json={"scenario": "ok"})
    request_id = resp.json()["request_id"]
    await _poll_until_done(client, request_id)

    health = (await client.get("/health")).json()

    assert health["processed"] >= 1
    assert health["succeeded"] >= 1
    assert health["handlers"]["primary"]["success"] >= 1


@pytest.mark.asyncio
async def test_get_unknown_request_returns_404(client):
    resp = await client.get("/requests/nonexistent-id")
    assert resp.status_code == 404
