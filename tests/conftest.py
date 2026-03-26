import pytest
from httpx import ASGITransport, AsyncClient

from app import metrics
from app.handlers import _attempt_tracker
from app.main import _requests, app


@pytest.fixture(autouse=True)
def clean_state():
    """Reset all module-level state between tests."""
    _requests.clear()
    _attempt_tracker.clear()
    metrics.reset()
    yield
    _requests.clear()
    _attempt_tracker.clear()
    metrics.reset()


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
