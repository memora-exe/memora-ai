import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

# Ensure .env is loaded from memora-ai root
_ai_root = Path(__file__).resolve().parent.parent.parent.parent
_env_path = _ai_root / ".env"
if _env_path.exists():
    load_dotenv(dotenv_path=_env_path, override=False)
else:
    load_dotenv(override=False)


@dataclass
class Settings:
    grpc_port: int = int(os.getenv("GRPC_PORT") or os.getenv("PORT") or "3020")
    max_workers: int = int(os.getenv("GRPC_MAX_WORKERS", "10"))
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_base_url: str = os.getenv("OPENAI_BASE_URL", "")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    llm_timeout_seconds: float = float(os.getenv("LLM_TIMEOUT_SECONDS", "30.0"))
    llm_max_retries: int = int(os.getenv("LLM_MAX_RETRIES", "1"))


settings = Settings()
