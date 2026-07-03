from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    groq_api_key: str | None = None
    openai_api_key: str | None = None
    alpha_vantage_api_key: str | None = None
    finnhub_api_key: str | None = None
    database_url: str | None = None

    primary_llm_provider: str = "groq"
    groq_model: str = "llama-3.3-70b-versatile"
    openai_model: str = "gpt-4.1-mini"

    request_timeout_seconds: float = 30.0
    # When true, the app can run completely locally without external API keys.
    # Real providers are used automatically when keys are configured.
    demo_mode: bool = True

    # Operational tuning
    log_level: str = "INFO"
    cache_ttl_seconds: float = 300.0  # market data / quote cache TTL
    monte_carlo_simulations: int = 2000
    sample_paths: int = 20

    def masked_summary(self) -> dict[str, bool]:
        """Return which secrets are configured without exposing values."""
        return {
            "groq_api_key": bool(self.groq_api_key),
            "openai_api_key": bool(self.openai_api_key),
            "alpha_vantage_api_key": bool(self.alpha_vantage_api_key),
            "finnhub_api_key": bool(self.finnhub_api_key),
            "database_url": bool(self.database_url),
            "demo_mode": bool(self.demo_mode),
        }


settings = Settings()
