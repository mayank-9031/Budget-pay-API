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
    
    # JWT / Security Configuration - PRODUCTION SETTINGS
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 720     # 12 hours - balance between security and user convenience
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30       # 30 days for refresh token
    
    # Google OAuth Token Configuration
    GOOGLE_TOKEN_EXPIRE_MINUTES: int = 720    # Match our access token expiry
    
    # Timezone Configuration
    TIMEZONE: str = "Asia/Kolkata"            # Indian Standard Time
    
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
    
    @property
    def is_supabase(self) -> bool:
        """Check if we're using Supabase database"""
        return "supabase.com" in self.DATABASE_URL
    
    @property
    def access_token_expire_seconds(self) -> int:
        """Get access token expiry in seconds"""
        return self.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    
    @property
    def refresh_token_expire_seconds(self) -> int:
        """Get refresh token expiry in seconds"""
        return self.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60
    
    @property
    def is_production(self) -> bool:
        """Check if running in production environment"""
        return self.ENVIRONMENT.lower() in ["production", "prod"]
    
    @property
    def is_development(self) -> bool:
        """Check if running in development environment"""
        return self.ENVIRONMENT.lower() in ["development", "dev"]
    
    def validate_production_config(self) -> list:
        """Validate configuration for production deployment"""
        issues = []
        
        if self.is_production:
            if self.SECRET_KEY == "your_secret_key_here_please_change_this_to_something_secure":
                issues.append("SECRET_KEY must be changed from default value in production")
            
            if len(str(self.SECRET_KEY)) < 32:
                issues.append("SECRET_KEY should be at least 32 characters long for production")
            
            if not self.SENDGRID_API_KEY or self.SENDGRID_API_KEY == "your_sendgrid_api_key_here":
                issues.append("SENDGRID_API_KEY must be configured for production")
            
            if not self.GOOGLE_CLIENT_ID or "your_google_client_id" in self.GOOGLE_CLIENT_ID:
                issues.append("GOOGLE_CLIENT_ID must be configured for production")
        
        return issues
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Debug print to verify settings are loaded
        if self.DEBUG:
            print(f"✅ Settings loaded with ACCESS_TOKEN_EXPIRE_MINUTES: {self.ACCESS_TOKEN_EXPIRE_MINUTES}")
        
        # Validate production configuration
        if self.is_production:
            issues = self.validate_production_config()
            if issues:
                print("⚠️ Production configuration issues:")
                for issue in issues:
                    print(f"   - {issue}")
                print("Please fix these issues before deploying to production.")

# Create a global settings instance
settings = Settings()