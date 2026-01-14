from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    DATABASE_URL: str
    QDRANT_URL: str
    QDRANT_COLECTION: str
    GOOGLE_API_KEY: str
    MYSQL_URL: str
    # GEMINI_API_KEY: str
    MODEL_GEMINI: str
    MODEL_EMBEDDING: str
    MODEL_RERANKING: str
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8"
    )

settings = Settings()