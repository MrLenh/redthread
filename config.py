"""Configuration management for the Lark Data Fetcher application."""

import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Application configuration."""

    # Lark API Credentials
    LARK_APP_ID = os.getenv("LARK_APP_ID", "")
    LARK_APP_SECRET = os.getenv("LARK_APP_SECRET", "")

    # Lark Base Configuration
    LARK_BASE_APP_TOKEN = os.getenv("LARK_BASE_APP_TOKEN", "")
    LARK_TABLE_ID = os.getenv("LARK_TABLE_ID", "")

    # Flask Configuration
    DEBUG = os.getenv("FLASK_DEBUG", "True").lower() == "true"
    HOST = os.getenv("FLASK_HOST", "127.0.0.1")
    PORT = int(os.getenv("FLASK_PORT", "5000"))

    # Paths
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    DATA_DIR = os.path.join(BASE_DIR, "data")
    ATTACHMENTS_DIR = os.path.join(BASE_DIR, "attachments")

    # Field names (customize based on your Lark Base schema)
    FACTORY_STATUS_FIELD = os.getenv("FACTORY_STATUS_FIELD", "Factory Status")
    ORDER_ID_FIELD = os.getenv("ORDER_ID_FIELD", "Order ID")

    @classmethod
    def validate(cls):
        """Validate required configuration."""
        required = [
            ("LARK_APP_ID", cls.LARK_APP_ID),
            ("LARK_APP_SECRET", cls.LARK_APP_SECRET),
            ("LARK_BASE_APP_TOKEN", cls.LARK_BASE_APP_TOKEN),
            ("LARK_TABLE_ID", cls.LARK_TABLE_ID),
        ]

        missing = [name for name, value in required if not value]

        if missing:
            raise ValueError(f"Missing required configuration: {', '.join(missing)}")

        return True

    @classmethod
    def ensure_directories(cls):
        """Ensure required directories exist."""
        os.makedirs(cls.DATA_DIR, exist_ok=True)
        os.makedirs(cls.ATTACHMENTS_DIR, exist_ok=True)
