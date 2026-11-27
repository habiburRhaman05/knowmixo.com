from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')

    # === Environment ===
    app_env: str = "development"
    public_app_url: str = "http://localhost:3000"
    backend_internal_url: str = "http://localhost:8000"

    # === Database (Neon PostgreSQL) ===
    database_url: str = ""  # postgresql://user:pass@host/db?sslmode=require

    # RLS-bound `app_user` role (ADR 002 / migration 0011), provisioned
    # per-environment by scripts/provision_app_user.py. Empty until that
    # script has been run; the live app's own request-serving pool does
    # not use this yet -- see migration 0011's docstring. Exists as a
    # declared field (rather than a raw os.environ read) so it goes
    # through the same .env loading and quote-stripping as every other
    # credential here, and so tests can read it via settings() instead of
    # needing it manually exported into the shell.
    database_url_app: str = ""

    # === Redis (native) ===
    redis_url: str = ""  # redis://user:pass@localhost:6379

    # === Pinecone Vector DB ===
    pinecone_api_key: str = ""
    pinecone_index_name: str = "knowmixo-rag-sa"
    pinecone_host: str = ""

    # === Cloudflare Embeddings ===
    cloudflare_account_id: str = ""
    cloudflare_api_token: str = ""
    embedding_model: str = "@cf/baai/bge-m3"
    embedding_dim: int = 1024

    # === Vector store (D3.3 dual-write, ADR 001) ===
    # Writes always go to BOTH Pinecone and pgvector (app/ingestion/pipeline.py).
    # This only controls which one CHAT RETRIEVAL reads from. Default stays
    # 'pinecone' (the already-proven read path) through the 72h dual-write
    # window; flips to 'pgvector' once hybrid retrieval (D3.4) is verified
    # against it.
    vector_store: str = "pinecone"

    # === Groq LLM ===
    groq_api_key: str = ""
    chat_model: str = "openai/gpt-oss-120b"
    free_only: bool = True  # Fail startup if paid routes would be reachable

    # === OpenRouter (ADR 004 fallback -- not in the live chain by default;
    # see app/providers/openrouter_chat.py's module docstring) ===
    openrouter_api_key: str = ""

    # === Reranker (RAG v2, launch/05-RAG-V2-SPEC.md) ===
    reranker_provider: str = "cloudflare"
    reranker_model: str = "@cf/baai/bge-reranker-base"
    jina_api_key: str = ""

    # === RAG engine (v1 = proven single-shot, v2 = multi-stage state machine) ===
    rag_engine: str = "v1"

    # === Budget enforcement ===
    global_chat_daily_limit: int = 1000
    company_chat_daily_limit: int = 100

    # === Google OAuth ===
    google_client_id: str = ""
    google_client_secret: str = ""

    # === Email (SMTP) ===
    smtp_host: str = "smtp.gmail.com"
    smtp_user: str = ""
    smtp_app_password: str = ""
    email_from: str = ""

    # === Auth.js / Sessions ===
    auth_secret: str = ""
    session_max_age_seconds: int = 604800  # 7 days

    # === Encryption ===
    encryption_key: str = ""  # 32-byte hex for AES-256

    # === Storage ===
    storage_backend: str = "local"  # 'local' or 's3'
    private_storage_dir: str = "/tmp/knowmivo-storage"
    max_file_bytes: int = 10485760  # 10 MiB
    max_crawl_pages: int = 20
    max_company_storage_bytes: int = 104857600  # 100 MiB

    # === Billing (Stripe, ADR 008) ===
    stripe_secret_key: str = ""
    stripe_publishable_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_tax_enabled: bool = True

    # === Channels: WhatsApp Cloud API + Meta (Messenger/Instagram) ===
    # D6.1/D6.4: live delivery PENDING_EXTERNAL on Meta business verification
    # and template approval -- code works standalone, no-ops when unset.
    channels_api_version: str = "v19.0"
    whatsapp_access_token: str = ""
    whatsapp_phone_number_id: str = ""
    whatsapp_business_account_id: str = ""
    whatsapp_webhook_verify_token: str = ""
    meta_app_secret: str = ""  # shared Meta app secret, HMACs webhook signatures for WhatsApp/Messenger/Instagram
    messenger_page_access_token: str = ""
    instagram_access_token: str = ""

    # === Slack app (D9.5): OAuth install + alerts channel delivery ===
    slack_client_id: str = ""
    slack_client_secret: str = ""

    # === Job runner tuning ===
    job_max_attempts: int = 4
    job_lease_seconds: int = 300

    # === Retention ===
    retention_days: int = 30

    # === Legacy AWS (disabled by default; only used if FREE_ONLY=false) ===
    aws_region: str = "us-east-1"
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    s3_bucket: str = ""
    bedrock_embed_model: str = ""
    bedrock_chat_model: str = ""

    # === Legacy Pinecone config (unused, kept for compatibility) ===
    pinecone_cloud: str = "aws"
    pinecone_region: str = "us-east-1"
    pinecone_ready_timeout: int = 180
    min_relevance: float = 0.25
    hitl_enabled: bool = False
    memory_turns: int = 6

    def __init__(self, **data):
        super().__init__(**data)
        # Startup validation: FREE_ONLY=true must forbid paid routes
        if self.free_only:
            if self.bedrock_embed_model or self.bedrock_chat_model or self.s3_bucket:
                raise ValueError(
                    "FREE_ONLY=true but AWS/Bedrock credentials are set. "
                    "Remove or set to empty strings to proceed."
                )
            if not self.groq_api_key:
                raise ValueError("FREE_ONLY=true requires GROQ_API_KEY to be set.")
            if not self.cloudflare_account_id or not self.cloudflare_api_token:
                raise ValueError(
                    "FREE_ONLY=true requires CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN."
                )

        # Require critical fields
        if not self.database_url:
            raise ValueError("DATABASE_URL is required.")
        if not self.redis_url:
            raise ValueError("REDIS_URL is required.")
        if not self.pinecone_api_key or not self.pinecone_host:
            raise ValueError("PINECONE_API_KEY and PINECONE_HOST are required.")

        # AUTH_SECRET gate: a short or empty secret in production makes
        # every signed artifact forgeable (escalation deep-link, API-key
        # HMAC, CSRF). Fail-closed in production; warn once in dev.
        # See launch/00-BUILD-HEALTH.md §2.3 and launch/03-RISKS-AND-BLOCKERS.md R02.
        if len(self.auth_secret) < 32:
            if self.app_env == "production":
                raise ValueError(
                    "AUTH_SECRET must be at least 32 bytes in production. "
                    "Generate one with: python -c 'import secrets; print(secrets.token_urlsafe(48))'"
                )
            import logging

            logging.getLogger(__name__).warning(
                "AUTH_SECRET is missing or shorter than 32 bytes. Fine in dev; "
                "required in production."
            )


@lru_cache
def settings() -> Settings:
    return Settings()