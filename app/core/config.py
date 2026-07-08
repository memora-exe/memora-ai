import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
    PORT = int(os.getenv("PORT", 8000))
    NESTJS_API_URL = os.getenv("NESTJS_API_URL", "http://localhost:3000")

    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1")
    HYBRID_TOP_K = int(os.getenv("HYBRID_TOP_K", "5"))
    HYBRID_TRAVERSE_DEPTH = int(os.getenv("HYBRID_TRAVERSE_DEPTH", "2"))
    HYBRID_MAX_NODES = int(os.getenv("HYBRID_MAX_NODES", "20"))

    # Phase 3 — AI Search / Node Summary / Document Reader
    SUMMARY_MODEL = os.getenv("SUMMARY_MODEL", "gemini-3.1")
    NODE_SUMMARY_MAX_TOKENS = int(os.getenv("NODE_SUMMARY_MAX_TOKENS", "1024"))
    DOC_SUMMARY_MAX_TOKENS = int(os.getenv("DOC_SUMMARY_MAX_TOKENS", "2048"))
    SEARCH_TOP_K = int(os.getenv("SEARCH_TOP_K", "10"))
    FOCAL_PADDING = float(os.getenv("FOCAL_PADDING", "1.4"))
    DOC_SUMMARY_INPUT_CAP = int(os.getenv("DOC_SUMMARY_INPUT_CAP", "80000"))

    DB_HOST = os.getenv("DB_REPO_HOST", "localhost")
    DB_PORT = int(os.getenv("DB_REPO_PORT", 5433))
    DB_USER = os.getenv("DB_REPO_USERNAME", "postgres")
    DB_PASSWORD = os.getenv("DB_REPO_PASSWORD", "postgres")
    DB_NAME = os.getenv("DB_REPO_NAME", "repo")

    RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5673/")

    REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT = int(os.getenv("REDIS_PORT", 6380))

settings = Settings()
