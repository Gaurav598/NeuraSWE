"""Application configuration loaded from environment variables.

Mirrors the .env.example file. Uses pydantic-settings for validation so the
process fails fast on misconfiguration instead of deep inside a request.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Server ---
    port: int = Field(default=3001, alias="PORT")
    host: str = Field(default="0.0.0.0", alias="HOST")
    node_env: str = Field(default="development", alias="NODE_ENV")
    log_level: str = Field(default="info", alias="LOG_LEVEL")
    cors_origins: str = Field(default="http://localhost:5173", alias="CORS_ORIGINS")

    # --- Database ---
    database_url: str = Field(
        default="postgresql+asyncpg://neuraswe:neuraswe@localhost:5432/neuraswe",
        alias="DATABASE_URL",
    )

    # --- Redis / Queue ---
    redis_url: str = Field(default="redis://localhost:6379", alias="REDIS_URL")
    worker_max_jobs: int = Field(default=2, alias="WORKER_MAX_JOBS")
    worker_job_timeout_s: int = Field(default=900, alias="WORKER_JOB_TIMEOUT_S")

    # --- Agent LLM provider ---
    llm_provider: str = Field(default="ollama", alias="LLM_PROVIDER")

    # --- Ollama ---
    ollama_url: str = Field(default="http://localhost:11434", alias="OLLAMA_URL")
    ollama_chat_model: str = Field(default="deepseek-coder-v2:16b", alias="OLLAMA_CHAT_MODEL")
    ollama_embed_model: str = Field(default="nomic-embed-text", alias="OLLAMA_EMBED_MODEL")
    ollama_embed_concurrency: int = Field(default=1, alias="OLLAMA_EMBED_CONCURRENCY")
    ollama_timeout_s: int = Field(default=180, alias="OLLAMA_TIMEOUT_S")

    # --- Hosted LLM provider (primary) ---
    # LLM_API_KEY may contain several comma-separated keys; the client rotates
    # across them when one is rate-limited.
    llm_api_key: str = Field(default="", alias="LLM_API_KEY")
    llm_base_url: str = Field(default="", alias="LLM_BASE_URL")
    llm_model: str = Field(default="", alias="LLM_MODEL")
    llm_timeout_s: int = Field(default=0, alias="LLM_TIMEOUT_S")
    # Per-key transient-error retries (network/5xx). 429s rotate immediately.
    llm_max_retries: int = Field(default=2, alias="LLM_MAX_RETRIES")
    # When true, build a fallback chain (primary -> other configured providers).
    llm_fallback_enabled: bool = Field(default=True, alias="LLM_FALLBACK_ENABLED")
    # Ordered provider pool for free-tier resilience. Supported names:
    # primary, gemini, openrouter, groq, ollama.
    llm_fallback_order: str = Field(
        default="primary,gemini,openrouter,groq,ollama",
        alias="LLM_FALLBACK_ORDER",
    )
    # Include local Ollama as the last fallback when hosted APIs are exhausted.
    llm_local_fallback_enabled: bool = Field(default=True, alias="LLM_LOCAL_FALLBACK_ENABLED")
    # Proactive pacing for the PRIMARY provider: cap requests/minute so we stay
    # under the free-tier RPM and never trigger a 429 in the first place.
    # 0 disables pacing. Default 15 matches Gemini free tier.
    llm_requests_per_minute: int = Field(default=15, alias="LLM_REQUESTS_PER_MINUTE")
    # Request hedging: fire every configured provider (including local Ollama) in
    # parallel each step and use the FIRST valid response, cancelling the rest.
    # This collapses per-step latency to the fastest provider and sidesteps a
    # slow/throttled one instead of waiting for it to time out. Costs more calls
    # per step (one per provider) but is dramatically faster on free tiers.
    llm_race_enabled: bool = Field(default=False, alias="LLM_RACE_ENABLED")
    # How long (seconds) to keep waiting for a *valid* racer after the first
    # response arrives, before accepting the best response seen so far.
    llm_race_grace_s: float = Field(default=0.0, alias="LLM_RACE_GRACE_S")

    # --- Fallback provider: Google Gemini (OpenAI-compatible endpoint) ---
    # 1M TPM on the free tier — best primary for a context-heavy agent loop.
    gemini_api_key: str = Field(default="", alias="GEMINI_API_KEY")
    gemini_model: str = Field(default="gemini-2.0-flash", alias="GEMINI_MODEL")
    gemini_base_url: str = Field(
        default="https://generativelanguage.googleapis.com/v1beta/openai",
        alias="GEMINI_BASE_URL",
    )
    gemini_requests_per_minute: int = Field(default=15, alias="GEMINI_REQUESTS_PER_MINUTE")

    # --- Fallback provider: Groq (fast, but only ~6K TPM on free tier) ---
    groq_api_key: str = Field(default="", alias="GROQ_API_KEY")
    groq_model: str = Field(default="llama-3.3-70b-versatile", alias="GROQ_MODEL")
    groq_base_url: str = Field(default="https://api.groq.com/openai/v1", alias="GROQ_BASE_URL")
    groq_requests_per_minute: int = Field(default=30, alias="GROQ_REQUESTS_PER_MINUTE")

    # --- Fallback provider: OpenRouter ---
    openrouter_api_key: str = Field(default="", alias="OPENROUTER_API_KEY")
    openrouter_model: str = Field(
        default="meta-llama/llama-3.3-70b-instruct:free", alias="OPENROUTER_MODEL"
    )
    openrouter_base_url: str = Field(
        default="https://openrouter.ai/api/v1", alias="OPENROUTER_BASE_URL"
    )
    openrouter_requests_per_minute: int = Field(
        default=20, alias="OPENROUTER_REQUESTS_PER_MINUTE"
    )
    # Backward-compatible aliases. Prefer LLM_* in new configs.
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    openai_base_url: str = Field(default="https://api.openai.com/v1", alias="OPENAI_BASE_URL")
    openai_model: str = Field(default="gpt-4.1-mini", alias="OPENAI_MODEL")
    openai_timeout_s: int = Field(default=180, alias="OPENAI_TIMEOUT_S")

    # --- ChromaDB ---
    chroma_url: str = Field(default="http://localhost:8000", alias="CHROMA_URL")

    # --- GitHub App ---
    github_app_id: str = Field(default="", alias="GITHUB_APP_ID")
    github_private_key_path: str = Field(default="", alias="GITHUB_PRIVATE_KEY_PATH")
    github_webhook_secret: str = Field(default="", alias="GITHUB_WEBHOOK_SECRET")
    # Optional simpler auth for local testing without a full GitHub App.
    github_pat: str = Field(default="", alias="GITHUB_PAT")
    github_default_base_branch: str = Field(default="main", alias="GITHUB_DEFAULT_BASE_BRANCH")

    # --- Jira integration ---
    jira_base_url: str = Field(default="", alias="JIRA_BASE_URL")
    jira_email: str = Field(default="", alias="JIRA_EMAIL")
    jira_api_token: str = Field(default="", alias="JIRA_API_TOKEN")
    jira_webhook_secret: str = Field(default="", alias="JIRA_WEBHOOK_SECRET")
    jira_auto_status: str = Field(default="NeuraSWE", alias="JIRA_AUTO_STATUS")
    # Comma-separated mapping: PROJECTKEY=owner/repo,OTHER=owner2/repo2
    jira_project_repo_map: str = Field(default="", alias="JIRA_PROJECT_REPO_MAP")

    # --- Agent config ---
    agent_max_steps: int = Field(default=25, alias="AGENT_MAX_STEPS")
    agent_step_timeout_ms: int = Field(default=120000, alias="AGENT_STEP_TIMEOUT_MS")
    agent_max_context_tokens: int = Field(default=8000, alias="AGENT_MAX_CONTEXT_TOKENS")
    agent_full_trajectory_steps: int = Field(default=10, alias="AGENT_FULL_TRAJECTORY_STEPS")

    # --- Sandbox ---
    sandbox_image: str = Field(default="neuraswe-sandbox:latest", alias="SANDBOX_IMAGE")
    sandbox_memory_mb: int = Field(default=2048, alias="SANDBOX_MEMORY_MB")
    sandbox_cpu_cores: float = Field(default=1.0, alias="SANDBOX_CPU_CORES")
    sandbox_workdir: str = Field(default="/workspace", alias="SANDBOX_WORKDIR")
    # When true, the agent runs commands on the host in a temp dir instead of
    # Docker. Useful for environments without a Docker daemon (CI, dev).
    sandbox_use_local: bool = Field(default=False, alias="SANDBOX_USE_LOCAL")

    @model_validator(mode="after")
    def normalize_llm_aliases(self) -> Settings:
        uses_provider_neutral_config = bool(
            self.llm_api_key or self.llm_base_url or self.llm_model or self.llm_timeout_s
        )
        if uses_provider_neutral_config:
            self.llm_base_url = self.llm_base_url or "https://api.openai.com/v1"
            self.llm_model = self.llm_model or "gpt-4.1-mini"
            self.llm_timeout_s = self.llm_timeout_s or 180
            return self

        self.llm_api_key = self.openai_api_key
        self.llm_base_url = self.openai_base_url
        self.llm_model = self.openai_model
        self.llm_timeout_s = self.openai_timeout_s
        return self

    @property
    def is_production(self) -> bool:
        return self.node_env.lower() == "production"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def agent_model_name(self) -> str:
        provider = self.llm_provider.strip().lower()
        if provider in {"openai", "openai-compatible", "compatible", "hosted"}:
            return self.llm_model
        return self.ollama_chat_model

    @property
    def jira_repo_map(self) -> dict[str, tuple[str, str]]:
        mapping: dict[str, tuple[str, str]] = {}
        for item in self.jira_project_repo_map.split(","):
            if "=" not in item:
                continue
            project_key, full_name = item.split("=", 1)
            if "/" not in full_name:
                continue
            owner, repo = full_name.split("/", 1)
            mapping[project_key.strip().upper()] = (owner.strip(), repo.strip())
        return mapping

    @property
    def jira_auto_status_list(self) -> set[str]:
        return {
            status.strip().lower()
            for status in self.jira_auto_status.split(",")
            if status.strip()
        }


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton."""
    return Settings()


settings = get_settings()
