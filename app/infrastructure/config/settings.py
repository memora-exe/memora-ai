import os
from dataclasses import dataclass


@dataclass
class Settings:
    grpc_port: int = int(os.getenv("GRPC_PORT", "50051"))
    max_workers: int = int(os.getenv("GRPC_MAX_WORKERS", "10"))
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "") or os.getenv("GOOGLE_API_KEY", "")
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")


settings = Settings()
