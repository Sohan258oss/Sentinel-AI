"""Central configuration.

Single source of truth for every knob in the platform. Nothing else in the
codebase may read ``os.environ`` directly — that keeps configuration auditable
and makes the whole system testable by swapping one object.
"""

from __future__ import annotations

from enum import Enum
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = BACKEND_ROOT.parent


class LLMProvider(str, Enum):
    GEMINI = "gemini"
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    MOCK = "mock"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_ROOT / ".env",
        env_prefix="SENTINEL_",
        extra="ignore",
        case_sensitive=False,
    )

    # -- Identity ------------------------------------------------------------
    app_name: str = "SentinelAI"
    app_tagline: str = "Predict. Coordinate. Respond. Recover."
    env: str = "development"
    log_level: str = "INFO"

    # -- LLM -----------------------------------------------------------------
    llm_provider: LLMProvider = LLMProvider.GEMINI
    llm_model: str = "gemini-2.0-flash"
    llm_reasoning_model: str = "gemini-2.0-flash-thinking-exp"
    llm_temperature: float = 0.2
    llm_max_retries: int = 3
    llm_timeout_seconds: int = 60

    google_api_key: str | None = None
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None

    #: Hard switch. When true the platform never touches the network: the LLM
    #: factory returns a scripted provider and every tool serves seeded data.
    #: This is what guarantees a live demo cannot fail.
    offline_mode: bool = False

    # -- External tool APIs (each optional, each with a fallback) -------------
    openweather_api_key: str | None = None
    newsapi_key: str | None = None
    mapbox_token: str | None = None

    # -- RAG -----------------------------------------------------------------
    knowledge_base_dir: Path = BACKEND_ROOT / "knowledge_base"
    vector_store_dir: Path = BACKEND_ROOT / ".chroma"
    vector_collection: str = "sentinel_doctrine"
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    rag_chunk_size: int = 900
    rag_chunk_overlap: int = 150
    rag_top_k: int = 5

    # -- Vision --------------------------------------------------------------
    vision_weights_path: Path = BACKEND_ROOT / "ml" / "artifacts" / "sentinel_cnn.pt"
    vision_upload_dir: Path = BACKEND_ROOT / "data" / "uploads"
    vision_use_vlm_ensemble: bool = True

    # -- Graph ---------------------------------------------------------------
    #: Upper bound on the reflection cycle. Prevents a pathological critique
    #: loop from burning tokens forever — a real cost control, not a formality.
    max_reflection_cycles: int = 2
    agent_timeout_seconds: int = 90

    # -- Data ----------------------------------------------------------------
    seed_data_dir: Path = BACKEND_ROOT / "data" / "seed"

    # -- API -----------------------------------------------------------------
    cors_origins: str | list[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"]
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    # -- Derived -------------------------------------------------------------
    @property
    def active_api_key(self) -> str | None:
        return {
            LLMProvider.GEMINI: self.google_api_key,
            LLMProvider.ANTHROPIC: self.anthropic_api_key,
            LLMProvider.OPENAI: self.openai_api_key,
            LLMProvider.MOCK: None,
        }[self.llm_provider]

    @property
    def is_live_llm(self) -> bool:
        """True only when a real model can actually be reached."""
        if self.offline_mode or self.llm_provider is LLMProvider.MOCK:
            return False
        return bool(self.active_api_key)

    def ensure_directories(self) -> None:
        for path in (self.vector_store_dir, self.vision_upload_dir, self.seed_data_dir):
            path.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_directories()
    return settings


settings = get_settings()
