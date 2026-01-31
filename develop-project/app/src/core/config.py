from pydantic_settings import BaseSettings, SettingsConfigDict
import os
class Settings(BaseSettings):
    DATABASE_URL: str
    QDRANT_URL: str
    QDRANT_COLECTION: str
    GOOGLE_API_KEY: str
    MODEL_GEMINI: str
    MODEL_EMBEDDING: str
    MODEL_RERANKING: str
    
    model_config = SettingsConfigDict(
        env_file=".env" if os.path.exists(".env") else None,
        env_file_encoding="utf-8"
    )

settings = Settings()