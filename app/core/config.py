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
    
    # Optional: Environment
    ENVIRONMENT: str = "development"
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Debug print to verify settings are loaded
        print(f"🔧 Settings loaded:")
        print(f"   - EMAIL_FROM: {self.EMAIL_FROM}")
        print(f"   - SENDGRID_API_KEY: {self.SENDGRID_API_KEY[:10]}...")
        print(f"   - FRONTEND_URL: {self.FRONTEND_URL}")
        print(f"   - BACKEND_BASE_URL: {self.BACKEND_BASE_URL}")

# Create a global settings instance
settings = Settings()