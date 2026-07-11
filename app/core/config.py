import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    PORT = int(os.getenv("PORT", 8000))
    NESTJS_API_URL = os.getenv("NESTJS_API_URL", "http://localhost:3000")

    # --- LLM dispatcher (OpenAI API spec, refactored 2026-07-09) ------------
    # All providers (OpenAI, OpenRouter, Azure, Gemini-OpenAI-compat proxy,
    # Ollama, vLLM, …) share the same wire format. Set OPENAI_BASE_URL +
    # OPENAI_API_KEY to point at the right endpoint. Examples:
    #   OpenAI:      https://api.openai.com/v1
    #   OpenRouter:  https://openrouter.ai/api/v1
    #   Azure:       https://<resource>.openai.azure.com/openai/deployments/<dep>
    #   Gemini*:     https://generativelanguage.googleapis.com/v1beta/openai/
    #   Ollama:      http://localhost:11434/v1
    OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL") or None
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or None
    OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    # --- Embeddings (also OpenAI /v1/embeddings) ----------------------------
    # Fallback to OPENAI_BASE_URL/OPENAI_API_KEY when *_EMBED_* is unset, so a
    # single key+URL pair can serve both chat and embeddings.
    OPENAI_EMBED_BASE_URL = os.getenv("OPENAI_EMBED_BASE_URL") or None
    OPENAI_EMBED_API_KEY = os.getenv("OPENAI_EMBED_API_KEY") or None
    OPENAI_EMBED_MODEL = os.getenv("OPENAI_EMBED_MODEL", "text-embedding-3-small")
    EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "1536"))
    PGVECTOR_COLUMN_DIM = int(os.getenv("PGVECTOR_COLUMN_DIM", "1536"))

    # Back-compat: Phase 1/2/3 code may still read SUMMARY_MODEL.
    SUMMARY_MODEL = os.getenv("SUMMARY_MODEL") or OPENAI_MODEL
    # Legacy alias kept for any stragglers reading GEMINI_MODEL.
    GEMINI_MODEL = os.getenv("GEMINI_MODEL") or OPENAI_MODEL

    HYBRID_TOP_K = int(os.getenv("HYBRID_TOP_K", "5"))
    HYBRID_TRAVERSE_DEPTH = int(os.getenv("HYBRID_TRAVERSE_DEPTH", "2"))
    HYBRID_MAX_NODES = int(os.getenv("HYBRID_MAX_NODES", "20"))

    # Phase 3 — AI Search / Node Summary / Document Reader
    NODE_SUMMARY_MAX_TOKENS = int(os.getenv("NODE_SUMMARY_MAX_TOKENS", "1024"))
    DOC_SUMMARY_MAX_TOKENS = int(os.getenv("DOC_SUMMARY_MAX_TOKENS", "2048"))
    SEARCH_TOP_K = int(os.getenv("SEARCH_TOP_K", "10"))
    FOCAL_PADDING = float(os.getenv("FOCAL_PADDING", "1.4"))
    DOC_SUMMARY_INPUT_CAP = int(os.getenv("DOC_SUMMARY_INPUT_CAP", "80000"))

    # Phase 4 — Learning Navigator (Roadmaps)
    ROADMAP_MODEL = os.getenv("ROADMAP_MODEL") or OPENAI_MODEL
    ROADMAP_TOPIC_EXTRACTION_MODEL = (
        os.getenv("ROADMAP_TOPIC_EXTRACTION_MODEL") or OPENAI_MODEL
    )
    ROADMAP_TOP_K_SEEDS = int(os.getenv("ROADMAP_TOP_K_SEEDS", "10"))
    ROADMAP_MAX_STAGES = int(os.getenv("ROADMAP_MAX_STAGES", "4"))
    ROADMAP_DOC_TEXT_CHAR_BUDGET = int(os.getenv("ROADMAP_DOC_TEXT_CHAR_BUDGET", "80000"))
    ROADMAP_MAX_FILE_IDS = int(os.getenv("ROADMAP_MAX_FILE_IDS", "5"))

    # Phase 4 — Knowledge Insights Dashboard
    INSIGHTS_RECOMMENDATIONS_MODEL = (
        os.getenv("INSIGHTS_RECOMMENDATIONS_MODEL") or OPENAI_MODEL
    )
    INSIGHTS_DEGREE_GAP_THRESHOLD = int(os.getenv("INSIGHTS_DEGREE_GAP_THRESHOLD", "2"))

    DB_HOST = os.getenv("DB_REPO_HOST", "localhost")
    DB_PORT = int(os.getenv("DB_REPO_PORT", 5433))
    DB_USER = os.getenv("DB_REPO_USERNAME", "postgres")
    DB_PASSWORD = os.getenv("DB_REPO_PASSWORD", "postgres")
    DB_NAME = os.getenv("DB_REPO_NAME", "repo")

    RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5673/")

    REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT = int(os.getenv("REDIS_PORT", 6380))


settings = Settings()


def validate_embedding_dim() -> None:
    """Fail fast at boot if EMBEDDING_DIM disagrees with the pgvector column."""
    if settings.EMBEDDING_DIM != settings.PGVECTOR_COLUMN_DIM:
        raise RuntimeError(
            f"EMBEDDING_DIM={settings.EMBEDDING_DIM} does not match "
            f"pgvector column dim={settings.PGVECTOR_COLUMN_DIM}. "
            "Either set EMBEDDING_DIM to match the schema or migrate "
            "document_chunk.embedding to a new dimension before proceeding."
        )
