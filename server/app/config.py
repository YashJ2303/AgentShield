from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import Optional


class Settings(BaseSettings):
    APP_NAME: str = "AgentShield Server"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False
    DATABASE_URL: str = Field(
        default="sqlite:///./agentshield.db",
        description="Database connection string (PostgreSQL or SQLite)",
    )
    ENV: str = Field(
        default="production",
        description="Deployment environment (dev, test, staging, production). Defaults to fail-safe production.",
    )
    DEFAULT_API_KEY: str = Field(
        default="agentshield-dev-key-12345",
        description="Default API key seeded only in dev/test environments",
    )
    ADMIN_TOKEN: Optional[str] = Field(
        default=None,
        description="Admin token required for policy mutations and approval decisions (must be set in env)",
    )
    OTLP_ENDPOINT: Optional[str] = Field(
        default=None,
        description="OTLP collector HTTP endpoint (e.g., http://localhost:4318/v1/traces)",
    )
    PRICING_CONFIG_PATH: Optional[str] = None
    APPROVAL_TIMEOUT_SECONDS: int = 60
    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    # --- Live external provider credentials -------------------------------------------
    # Every credential below is OPTIONAL. AgentShield is designed to run end-to-end with
    # zero keys: any provider that is not configured falls back to a high-fidelity local
    # simulation that is explicitly labelled as such in every span, API response, and
    # dashboard badge. See server/app/services/live_integrations.py provider_statuses().
    GEMINI_API_KEY: Optional[str] = Field(
        default=None,
        description="Google Gemini API key. Enables real gemini-* model inference through the LLM proxy.",
    )
    OPENAI_API_KEY: Optional[str] = Field(
        default=None,
        description="OpenAI API key. Enables real gpt-* inference and live content moderation.",
    )
    OPENAI_BASE_URL: str = Field(
        default="https://api.openai.com/v1",
        description="OpenAI-compatible endpoint base. Point at a proxy or self-hosted gateway if needed.",
    )
    STRIPE_API_KEY: Optional[str] = Field(
        default=None,
        description="Stripe secret key (sk_...). Enables real PaymentIntent creation in live test mode.",
    )
    STRIPE_API_BASE: str = Field(default="https://api.stripe.com/v1", description="Stripe API base URL.")
    SENDGRID_API_KEY: Optional[str] = Field(
        default=None,
        description="SendGrid API key. Enables real outbound email dispatch (still PII-redacted first).",
    )
    SLACK_BOT_TOKEN: Optional[str] = Field(
        default=None,
        description="Slack bot token (xoxb-...). Enables real chat.postMessage dispatch (PII-redacted first).",
    )
    TWILIO_ACCOUNT_SID: Optional[str] = Field(default=None, description="Twilio account SID for SMS dispatch.")
    TWILIO_AUTH_TOKEN: Optional[str] = Field(default=None, description="Twilio auth token for SMS dispatch.")
    URLSCAN_API_KEY: Optional[str] = Field(
        default=None,
        description="urlscan.io API key. Optional; the public read-only search endpoint works without one.",
    )

    # --- Live integration behaviour --------------------------------------------------
    LIVE_ALLOW_NETWORK: bool = Field(
        default=True,
        description="Master switch for outbound HTTP to third-party APIs. Set false for hermetic demos/tests.",
    )
    LIVE_HTTP_TIMEOUT_SECONDS: float = Field(
        default=6.0,
        ge=0.1,
        le=60.0,
        description="Per-request timeout for outbound live provider calls.",
    )
    LIVE_SIMULATE_WHEN_UNKEYED: bool = Field(
        default=True,
        description="When a keyed provider is missing, run the labelled simulation instead of failing closed.",
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )



settings = Settings()
