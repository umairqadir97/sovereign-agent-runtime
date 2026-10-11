"""Unit tests for Pydantic Settings and sovereign configuration validation."""

from runtime.config import SovereignCloudProvider, SovereignConfig, SovereignRegion


def test_default_config_values() -> None:
    config = SovereignConfig()
    assert config.CLOUD_PROVIDER == SovereignCloudProvider.GCP_VERTEX
    assert SovereignRegion.QATAR_CENTRAL.value in config.ALLOWED_RESIDENCY_REGIONS
    assert config.STRICT_DATA_RESIDENCY is True
    assert config.REDIS_TLS_ENABLED is True
    assert "cryptoKeys" in config.CMEK_KEY_ID


def test_allowed_regions_parsing() -> None:
    config = SovereignConfig(
        ALLOWED_RESIDENCY_REGIONS=["me-central1", "me-central-1"]  # type: ignore
    )
    assert len(config.ALLOWED_RESIDENCY_REGIONS) == 2
    assert "me-central1" in config.ALLOWED_RESIDENCY_REGIONS
