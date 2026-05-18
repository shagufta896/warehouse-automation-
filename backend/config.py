"""
Configuration management for the application
"""
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # --- existing fields (keep as-is) ---
    APP_TITLE:       str  = "StockSense API"
    APP_VERSION:     str  = "3.0.0"
    DATABASE_URL:    str  = "sqlite:///./inventory.db"
    UPLOAD_FOLDER:   str  = "app/uploads"
    MODEL_FOLDER:    str  = "app/ml/models"
    MAX_FILE_SIZE:   int  = 10 * 1024 * 1024
    ALLOWED_ORIGINS: list = ["*"]

    # --- NEW: JWT ---
    SECRET_KEY:      str  = "change-me-in-production-use-a-long-random-string"
    JWT_ALGORITHM:   str  = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440   # 24 hours

    # --- NEW: SMTP (leave blank in dev — OTP prints to console) ---
    SMTP_HOST:  str  = ""
    SMTP_PORT:  int  = 587
    SMTP_TLS:   bool = True
    SMTP_USER:  str  = ""
    SMTP_PASS:  str  = ""
    SMTP_FROM:  str  = "noreply@stocksense.app"
    
    LOG_LEVEL: str = "INFO"

    class Config:
        env_file = ".env"


settings = Settings()