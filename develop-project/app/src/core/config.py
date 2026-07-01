from pydantic_settings import BaseSettings, SettingsConfigDict
import os
class Settings(BaseSettings):
    DATABASE_URL: str
    QDRANT_URL: str
    QDRANT_COLECTION: str
    HF_TOKEN: str
    MODEL_EMBEDDING: str
    MODEL_RERANKING: str
    LLM_URL: str
    MODEL_LLM: str
    LLM_API_KEY: str
    LLM_TEMPERATURE: float
    LLM_TOP_P: float
    LIMIT_SEARCH_RESULTS: int
    MIN_SCORE: float
    TOP_K_RERANK: int

    
    model_config = SettingsConfigDict(
        env_file=".env" if os.path.exists(".env") else None,
        env_file_encoding="utf-8"
    )

settings = Settings()