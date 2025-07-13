# app/core/config.py

import os
from pathlib import Path
from typing import Union
from pydantic import EmailStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Get the project root directory (where .env should be located)
BASE_DIR = Path(__file__).resolve().parent.parent.parent

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding='utf-8',
        case_sensitive=True,
        extra="ignore"
    )
    
    # App Configuration
    APP_NAME: str = "Budget Pay API"
    DEBUG: bool = False
    VERSION: str = "1.0.0"
    
    # Database Configuration
    DATABASE_URL: str
    
    # JWT / Security Configuration
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 10080
    
    # CORS Configuration
    FRONTEND_URL: str
    
    # SendGrid Configuration
    SENDGRID_API_KEY: str
    EMAIL_FROM: EmailStr
    EMAIL_FROM_NAME: str = "Budget Pay Team"
    
    # Backend Configuration
    BACKEND_BASE_URL: str
    
    # AI Chatbot Configuration
    GROQ_API_KEY: str
    OPENROUTER_API_KEY: str = ""  # New: OpenRouter API key
    
    # Google OAuth Configuration
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = ""
    
    # Optional: Environment
    ENVIRONMENT: str = "development"
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Debug print to verify settings are loaded

# Create a global settings instance
settings = Settings()