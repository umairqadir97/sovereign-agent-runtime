"""Runtime configuration management via Pydantic Settings.

Provides deterministic environment parsing, customer-managed encryption key (CMEK)
configurations, VPC boundary enforcement parameters, and sovereign cloud residency mappings.
"""

import json
from enum import StrEnum
from functools import lru_cache
from typing import Any, Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import (
    BaseSettings,
    DotEnvSettingsSource,
    EnvSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)


class SovereignCloudProvider(StrEnum):
    """Supported sovereign cloud hyperscaler infrastructure backends."""

    GCP_VERTEX = "gcp_vertex"
    AWS_BEDROCK = "aws_bedrock"
    AZURE_SOVEREIGN = "azure_sovereign"
    AIR_GAPPED = "air_gapped"


class SovereignRegion(StrEnum):
    """Regulated sovereign cloud regions with in-country data residency mandates."""

    # Middle East Sovereign Regions (e.g., Qatar National Cyber Security Agency & UAE DESC)
    QATAR_CENTRAL = "me-central1"  # Doha
    UAE_CENTRAL = "me-central-1"  # Abu Dhabi / Dubai
    KSA_CENTRAL = "me-central2"  # Dammam

    # European Sovereign Cloud
    EU_FRANKFURT = "eu-central-1"  # Germany
    EU_PARIS = "eu-west-3"  # France

    # Default Air-Gapped / Isolated Enclave
    AIR_GAPPED_LOCAL = "isolated-enclave-01"


class VPCEgressMode(StrEnum):
    """Network egress isolation level enforcing zero external leakage."""

    AIR_GAPPED = "AIR_GAPPED"
    RESTRICTED_SOVEREIGN = "RESTRICTED_SOVEREIGN"
    ALLOW_ALL = "ALLOW_ALL"


class SovereignEnvSource(EnvSettingsSource):
    """Custom environment source supporting comma-separated or JSON list strings."""

    def prepare_field_value(
        self, field_name: str, field: Any, value: Any, value_is_complex: bool
    ) -> Any:
        if field_name in (
            "ALLOWED_RESIDENCY_REGIONS",
            "AUTHORIZED_EGRESS_CIDRS",
            "CORS_ALLOW_ORIGINS",
        ) and isinstance(value, str):
            try:
                return json.loads(value)
            except Exception:
                return [x.strip() for x in value.split(",") if x.strip()]
        return super().prepare_field_value(field_name, field, value, value_is_complex)


class SovereignDotEnvSource(DotEnvSettingsSource):
    """Custom dotenv source supporting comma-separated or JSON list strings."""

    def prepare_field_value(
        self, field_name: str, field: Any, value: Any, value_is_complex: bool
    ) -> Any:
        if field_name in (
            "ALLOWED_RESIDENCY_REGIONS",
            "AUTHORIZED_EGRESS_CIDRS",
            "CORS_ALLOW_ORIGINS",
        ) and isinstance(value, str):
            try:
                return json.loads(value)
            except Exception:
                return [x.strip() for x in value.split(",") if x.strip()]
        return super().prepare_field_value(field_name, field, value, value_is_complex)


class SovereignConfig(BaseSettings):
    """Enterprise runtime configuration with VPC, CMEK, and sovereignty guarantees."""

    model_config = SettingsConfigDict(
        env_prefix="SOVEREIGN_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            SovereignEnvSource(settings_cls),
            SovereignDotEnvSource(settings_cls),
            file_secret_settings,
        )

    # Core Environment & Identity
    ENVIRONMENT: Literal["development", "staging", "production"] = "production"
    SERVICE_NAME: str = "sovereign-agent-runtime"
    TENANT_ID_DEFAULT: str = "sovereign-enterprise-root"

    # Cloud Provider & Sovereign Region Boundary
    CLOUD_PROVIDER: SovereignCloudProvider = SovereignCloudProvider.GCP_VERTEX
    DEFAULT_RESIDENCY_REGION: SovereignRegion = SovereignRegion.QATAR_CENTRAL
    ALLOWED_RESIDENCY_REGIONS: list[str] = Field(
        default_factory=lambda: [
            SovereignRegion.QATAR_CENTRAL.value,
            SovereignRegion.UAE_CENTRAL.value,
            SovereignRegion.KSA_CENTRAL.value,
            SovereignRegion.EU_FRANKFURT.value,
            SovereignRegion.AIR_GAPPED_LOCAL.value,
        ]
    )
    STRICT_DATA_RESIDENCY: bool = Field(
        default=True,
        description="When True, rejects any execution if the target region is outside allowed boundaries.",
    )

    # Customer-Managed Encryption Key (CMEK) Configuration
    CMEK_KEY_ID: str = Field(
        default="projects/sovereign-core-prod/locations/me-central1/keyRings/agent-state-ring/cryptoKeys/session-cmek-k1",
        description="Full resource ID or ARN of the Customer Managed Encryption Key.",
    )
    CMEK_KEY_VERSION: str | None = Field(
        default="1",
        description="Active CMEK cryptographic version used for envelope encryption.",
    )
    CMEK_ROTATION_PERIOD_DAYS: int = Field(default=90, ge=30, le=365)

    # VPC Service Controls & Air-Gapped Network Boundaries
    VPC_SERVICE_PERIMETER_ID: str | None = Field(
        default="accessPolicies/718293041/servicePerimeters/sovereign_perimeter_me_central1",
        description="Hyperscaler VPC Service Controls boundary perimeter identifier.",
    )
    VPC_EGRESS_MODE: VPCEgressMode = VPCEgressMode.RESTRICTED_SOVEREIGN
    AUTHORIZED_EGRESS_CIDRS: list[str] = Field(
        default_factory=lambda: ["10.240.0.0/16", "172.16.0.0/12"]
    )

    # Redis Distributed State Persistence & Checkpointing
    REDIS_URL: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL for durable LangGraph checkpointing.",
    )
    REDIS_TLS_ENABLED: bool = True
    REDIS_KEY_PREFIX: str = "sovereign:state:"
    REDIS_STATE_TTL_SECONDS: int = Field(default=86400 * 7, ge=3600)  # 7 days

    # Model / Reasoning Engine Endpoints (Sovereign Enclave)
    MODEL_ID: str = "gemini-1.5-pro-preview-0514"
    MODEL_TEMPERATURE: float = Field(default=0.0, ge=0.0, le=1.0)
    MODEL_MAX_OUTPUT_TOKENS: int = Field(default=4096, ge=128, le=32768)
    MODEL_INVOCATION_TIMEOUT_SECONDS: float = Field(default=30.0, gt=0.0)

    # Tool Execution & Circuit Breakers
    TOOL_TIMEOUT_SECONDS: float = Field(default=15.0, gt=0.0)
    CIRCUIT_BREAKER_FAILURE_THRESHOLD: int = Field(default=5, ge=1)
    CIRCUIT_BREAKER_RECOVERY_TIMEOUT_SECONDS: float = Field(default=60.0, ge=5.0)

    # Observability & OpenTelemetry
    OTEL_EXPORTER_OTLP_ENDPOINT: str | None = Field(
        default=None,
        description="OTLP collector endpoint (e.g. http://otel-collector.monitoring:4317).",
    )
    OTEL_SAMPLE_RATE: float = Field(default=1.0, ge=0.0, le=1.0)

    # API Server Configuration
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    API_WORKERS: int = 4
    CORS_ALLOW_ORIGINS: list[str] = Field(default_factory=lambda: ["*"])
    SECRET_KEY: SecretStr = Field(
        default=SecretStr("sovereign-production-key-change-in-production-env-min32bytes")
    )

    @field_validator("ALLOWED_RESIDENCY_REGIONS", mode="before")
    @classmethod
    def _parse_allowed_regions(cls, v: object) -> list[str]:
        if isinstance(v, str):
            return [x.strip() for x in v.split(",") if x.strip()]
        if isinstance(v, list):
            return [str(x) for x in v]
        return []


@lru_cache(maxsize=1)
def get_settings() -> SovereignConfig:
    """Retrieve cached singleton application settings."""
    return SovereignConfig()
