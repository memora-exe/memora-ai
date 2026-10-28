import os
from dataclasses import dataclass


@dataclass
class Settings:
    grpc_port: int = int(os.getenv("GRPC_PORT", "50051"))
    max_workers: int = int(os.getenv("GRPC_MAX_WORKERS", "10"))
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_base_url: str = os.getenv("OPENAI_BASE_URL", "")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")


settings = Settings()
