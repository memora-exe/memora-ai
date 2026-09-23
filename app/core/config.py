import os
from pathlib import Path
from dotenv import load_dotenv

env_path = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(dotenv_path=env_path, override=True)


class Settings:
    PORT = int(os.getenv("PORT", 3020))
    NESTJS_API_URL = os.getenv("NESTJS_API_URL", "http://localhost:3010")
    MEMORA_INTERNAL_TOKEN = os.getenv("MEMORA_INTERNAL_TOKEN") or ""
    GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY") or None

    OPENAI_BASE_URL = "https://router.kepter.id.vn/v1"
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or None
    OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    AI_REASONING_EFFORT = os.getenv("AI_REASONING_EFFORT") or None
    AI_TEMPERATURE = float(os.getenv("AI_TEMPERATURE", "0.2"))

    STORAGE_BASE_DIR = os.getenv(
        "STORAGE_BASE_DIR",
        str(Path(__file__).resolve().parents[2] / "storage"),
    )

    CHAT_LLM_TIMEOUT_SEC = int(os.getenv("CHAT_LLM_TIMEOUT_SEC", "60"))
    CHAT_TURN_DEADLINE_SEC = int(os.getenv("CHAT_TURN_DEADLINE_SEC", "180"))

    INGESTION_CONCURRENCY = int(os.getenv("INGESTION_CONCURRENCY", "4"))
    INGESTION_LLM_TIMEOUT_SEC = int(os.getenv("INGESTION_LLM_TIMEOUT_SEC", "45"))
    INGESTION_TEXT_CHAR_CAP = int(os.getenv("INGESTION_TEXT_CHAR_CAP", "15000"))
    INGESTION_PIPELINE_TIMEOUT_SEC = int(os.getenv("INGESTION_PIPELINE_TIMEOUT_SEC", "120"))

    NODE_SUMMARY_MAX_TOKENS = int(os.getenv("NODE_SUMMARY_MAX_TOKENS", "1024"))
    DOC_SUMMARY_MAX_TOKENS = int(os.getenv("DOC_SUMMARY_MAX_TOKENS", "2048"))
    SEARCH_TOP_K = int(os.getenv("SEARCH_TOP_K", "10"))
    FOCAL_PADDING = float(os.getenv("FOCAL_PADDING", "1.4"))
    DOC_SUMMARY_INPUT_CAP = int(os.getenv("DOC_SUMMARY_INPUT_CAP", "80000"))

    ROADMAP_TOP_K_SEEDS = int(os.getenv("ROADMAP_TOP_K_SEEDS", "10"))
    ROADMAP_MAX_STAGES = int(os.getenv("ROADMAP_MAX_STAGES", "4"))
    ROADMAP_DOC_TEXT_CHAR_BUDGET = int(os.getenv("ROADMAP_DOC_TEXT_CHAR_BUDGET", "80000"))
    ROADMAP_MAX_FILE_IDS = int(os.getenv("ROADMAP_MAX_FILE_IDS", "5"))

    INSIGHTS_DEGREE_GAP_THRESHOLD = int(os.getenv("INSIGHTS_DEGREE_GAP_THRESHOLD", "2"))

    DB_HOST = os.getenv("DB_REPO_HOST", "localhost")
    DB_PORT = int(os.getenv("DB_REPO_PORT", 5433))
    DB_USER = os.getenv("DB_REPO_USERNAME", "postgres")
    DB_PASSWORD = os.getenv("DB_REPO_PASSWORD", "postgres")
    DB_NAME = os.getenv("DB_REPO_NAME", "repo")

    RABBITMQ_ENABLED = (
        os.getenv("RABBITMQ_ENABLED", "false").lower() in ("true", "1", "yes")
    )
    RABBITMQ_URL = os.getenv("CLOUDAMQP_URL") or os.getenv(
        "RABBITMQ_URL", "amqp://guest:guest@localhost:5673/"
    )

    REDIS_URL = os.getenv("REDIS_URL") or None
    REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT = int(os.getenv("REDIS_PORT", 6380))


settings = Settings()
