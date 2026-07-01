import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
    PORT = int(os.getenv("PORT", 8000))
    NESTJS_API_URL = os.getenv("NESTJS_API_URL", "http://localhost:3000")

settings = Settings()
