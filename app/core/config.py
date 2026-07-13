import os
from dotenv import load_dotenv

# override=True so a fresh `.env` edit always wins over shell exports.
# Without this, `export OPENAI_EMBED_MODEL=text-embedding-3-small` set once
# in a terminal persists across `.env` edits, and the user sees "embed fails
# even though I changed .env" — silent override, very confusing.
load_dotenv(override=True)

class Settings:
    PORT = int(os.getenv("PORT", 8000))
    NESTJS_API_URL = os.getenv("NESTJS_API_URL", "http://localhost:3000")
    # Shared secret for service-to-service internal endpoints on NestJS
    # (/internal/files/:id/status). Required for the cancel/status sync paths
    # in rabbitmq_consumer.py. The same value MUST be set as
    # MEMORA_INTERNAL_TOKEN on the BE side, where InternalTokenGuard compares
    # it against the X-Internal-Token header.
    MEMORA_INTERNAL_TOKEN = os.getenv("MEMORA_INTERNAL_TOKEN") or ""

    # Legacy Google AI key — still consumed by agent_service.py which uses
    # google-genai / google-adk (those SDKs read GOOGLE_API_KEY from os.environ).
    # Not used by the OpenAI-spec dispatcher below.
    GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY") or None

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
    # NOTE: the previous default (`text-embedding-3-small`) is an OpenAI-only
    # model id; on OpenRouter-compat proxies it returns 200 OK with empty
    # `data: []` and the SDK raises `ValueError("No embedding data received")`.
    # Set OPENAI_EMBED_MODEL in .env to whatever your proxy actually exposes,
    # e.g. `openrouter/nvidia/llama-nemotron-embed-vl-1b-v2:free` (768-dim).
    OPENAI_EMBED_MODEL = os.getenv("OPENAI_EMBED_MODEL", "text-embedding-3-small")
    # DB schema is `document_chunk.embedding vector(768)` (see
    # docs/plans/phase-1-diagrams.md). The dim defaults here MUST match —
    # validate_embedding_dim() refuses to boot otherwise, and silent mismatch
    # surfaces as a pgvector dimension error on the first insert.
    EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "1536"))
    PGVECTOR_COLUMN_DIM = int(os.getenv("PGVECTOR_COLUMN_DIM", "1536"))
    # Phase 5 — Embedding fan-out tuning (refactored 2026-07-12 to fix
    # "AI stuck embedding after file delete" + "ingestion takes 20+ min on
    # big files"). Default batch_size=1 dodges a proxy that returns empty
    # data on bulk /v1/embeddings payloads; concurrency=8 runs N single-chunk
    # requests in parallel instead of serially. Tune via .env.
    EMBED_BATCH_SIZE = int(os.getenv("EMBED_BATCH_SIZE", "1"))
    EMBED_CONCURRENCY = int(os.getenv("EMBED_CONCURRENCY", "8"))
    # Hard cap on total wall-clock for a single file's embed stage. If exceeded
    # (proxy stuck, network dead) we abort and mark the file failed instead of
    # burning the whole ingestion slot for hours. 0 = no cap.
    EMBED_STAGE_TIMEOUT_SEC = int(os.getenv("EMBED_STAGE_TIMEOUT_SEC", "0"))
    # Per-request cap on a single /v1/embeddings call. If the proxy stalls,
    # this raises asyncio.TimeoutError inside _run_one so the retry budget
    # kicks in instead of hanging forever. ponytail: bump to 60s if the
    # upstream legitimately needs >30s for big batch payloads.
    EMBED_PER_REQUEST_TIMEOUT_SEC = int(os.getenv("EMBED_PER_REQUEST_TIMEOUT_SEC", "30"))
    # Hard cap on a single chat turn (non-stream + stream). Without this,
    # LiteLLM `acompletion(stream=True)` waits for the first upstream chunk
    # forever when the proxy drops the connection mid-stream.
    CHAT_LLM_TIMEOUT_SEC = int(os.getenv("CHAT_LLM_TIMEOUT_SEC", "90"))
    # ponytail: OUTER overall turn deadline. `CHAT_LLM_TIMEOUT_SEC` only wraps
    # individual `__anext__()` calls inside `_aiter_with_timeout`, so if the
    # runner blocks inside a single tool HTTP call (e.g. llm_search_hybrid
    # waiting on a starved LiteLLM pool during file ingest), per-step never
    # fires. CHAT_TURN_DEADLINE_SEC is the hard cap on the whole turn so the
    # SSE stream always closes within a bounded window.
    CHAT_TURN_DEADLINE_SEC = int(os.getenv("CHAT_TURN_DEADLINE_SEC", "180"))

    HYBRID_TOP_K = int(os.getenv("HYBRID_TOP_K", "5"))
    HYBRID_TRAVERSE_DEPTH = int(os.getenv("HYBRID_TRAVERSE_DEPTH", "2"))
    HYBRID_MAX_NODES = int(os.getenv("HYBRID_MAX_NODES", "20"))

    # Phase 3 — AI Search / Node Summary / Document Reader
    NODE_SUMMARY_MAX_TOKENS = int(os.getenv("NODE_SUMMARY_MAX_TOKENS", "1024"))
    DOC_SUMMARY_MAX_TOKENS = int(os.getenv("DOC_SUMMARY_MAX_TOKENS", "2048"))
    SEARCH_TOP_K = int(os.getenv("SEARCH_TOP_K", "10"))
    FOCAL_PADDING = float(os.getenv("FOCAL_PADDING", "1.4"))
    DOC_SUMMARY_INPUT_CAP = int(os.getenv("DOC_SUMMARY_INPUT_CAP", "80000"))

    # Phase 4 — Learning Navigator (Roadmaps) — all use OPENAI_MODEL
    ROADMAP_TOP_K_SEEDS = int(os.getenv("ROADMAP_TOP_K_SEEDS", "10"))
    ROADMAP_MAX_STAGES = int(os.getenv("ROADMAP_MAX_STAGES", "4"))
    ROADMAP_DOC_TEXT_CHAR_BUDGET = int(os.getenv("ROADMAP_DOC_TEXT_CHAR_BUDGET", "80000"))
    ROADMAP_MAX_FILE_IDS = int(os.getenv("ROADMAP_MAX_FILE_IDS", "5"))

    # Phase 4 — Knowledge Insights Dashboard — all use OPENAI_MODEL
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