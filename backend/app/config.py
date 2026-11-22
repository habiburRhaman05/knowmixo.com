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

    # === Groq LLM ===
    groq_api_key: str = ""
    chat_model: str = "openai/gpt-oss-120b"
    free_only: bool = True  # Fail startup if paid routes would be reachable

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


@lru_cache
def settings() -> Settings:
    return Settings()