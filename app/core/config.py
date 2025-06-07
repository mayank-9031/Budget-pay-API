# app/core/config.py
import os
from pathlib import Path
from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).resolve().parent.parent

class Settings(BaseSettings):
    # Database
    POSTGRES_USER: str = os.getenv("POSTGRES_USER", "postgres")
    POSTGRES_PASSWORD: str = os.getenv("POSTGRES_PASSWORD", "postgres")
    POSTGRES_SERVER: str = os.getenv("POSTGRES_SERVER", "localhost")
    POSTGRES_PORT: str = "5432"
    POSTGRES_DB: str = os.getenv("POSTGRES_DB","postgres") 
    
    @property
    def DATABASE_URL(self) -> str:
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    # JWT / Security
    SECRET_KEY: str = os.getenv("SECRET_KEY", "oI0oND9kSXtTMzCriYZ8UVp7XoDLQwH74HsBiLRtgQ8")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 10800

    class Config:
        env_file = BASE_DIR / ".env"
        case_sensitive = True

settings = Settings()