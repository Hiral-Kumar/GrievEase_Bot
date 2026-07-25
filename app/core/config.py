"""
Centralized configuration, loaded from environment variables (.env).
Keeping all settings in one place avoids magic strings scattered across the codebase.
"""
import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    # LLM
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    CLAUDE_MODEL: str = os.getenv("CLAUDE_MODEL", "claude-sonnet-5")

    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./app/data/grievance.db")

    # Notifications (SMTP) — used by services/notification_service.py
    SMTP_HOST: str = os.getenv("SMTP_HOST", "")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER: str = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
    NOTIFY_FROM_EMAIL: str = os.getenv("NOTIFY_FROM_EMAIL", "notifications@gbu.ac.in")

    # If no real SMTP credentials are configured, notifications are logged instead
    # of actually sent — keeps local development and grading frictionless.
    @property
    def SMTP_CONFIGURED(self) -> bool:
        return bool(self.SMTP_HOST and self.SMTP_USER and self.SMTP_PASSWORD)


settings = Settings()
