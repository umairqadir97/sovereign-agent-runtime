"""Pytest global fixtures and runtime environment configuration."""

import pytest
from httpx import ASGITransport, AsyncClient

from runtime.config import get_settings
from runtime.graph import compile_sovereign_graph
from runtime.server import app
from runtime.tools import default_registry


@pytest.fixture(autouse=True)
def reset_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure clean default sovereign settings for every test run."""
    monkeypatch.setenv("SOVEREIGN_ENVIRONMENT", "development")
    monkeypatch.setenv("SOVEREIGN_STRICT_DATA_RESIDENCY", "true")
    monkeypatch.setenv(
        "SOVEREIGN_ALLOWED_RESIDENCY_REGIONS",
        "me-central1,me-central-1,me-central2,eu-central-1,isolated-enclave-01",
    )
    get_settings.cache_clear()


@pytest.fixture
def mock_app_state() -> None:
    """Initialize app.state for FastAPI tests without full lifespan."""
    app.state.graph = compile_sovereign_graph(registry=default_registry)


@pytest.fixture
async def async_client(mock_app_state: None) -> AsyncClient:
    """Async HTTP test client bound to FastAPI application."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client
