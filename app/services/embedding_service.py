import time
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from app.core.config import settings

class EmbeddingService:
    def __init__(self):
        self.embeddings = GoogleGenerativeAIEmbeddings(
            model="models/embedding-001",
            google_api_key=settings.GOOGLE_API_KEY
        )

    def get_embedding(self, text: str) -> list[float]:
        return self.get_embeddings([text])[0]

    def get_embeddings(self, texts: list[str]) -> list[list[float]]:
        results = []
        batch_size = 100
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]

            retries = 5
            backoff = 1.0
            for attempt in range(retries):
                try:
                    # Retrieve embeddings for the batch
                    embeddings_batch = self.embeddings.embed_documents(batch)
                    results.extend(embeddings_batch)
                    break
                except Exception as e:
                    if attempt == retries - 1:
                        raise e
                    time.sleep(backoff)
                    backoff *= 2.0
        return results

embedding_service = EmbeddingService()
