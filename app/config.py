import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./dev.db")

APP_NAME = os.getenv("APP_NAME", "Team Task Tracker")
APP_VERSION = "0.2.0"
APP_HOST = os.getenv("APP_HOST", "0.0.0.0")
APP_PORT = int(os.getenv("APP_PORT", "8000"))
DEBUG = os.getenv("DEBUG", "false").lower() == "true"

SENTRY_DSN = os.getenv("SENTRY_DSN", "")
SENTRY_ENVIRONMENT = os.getenv("SENTRY_ENVIRONMENT", "development")
SENTRY_TRACES_SAMPLE_RATE = float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "1.0"))

AUTH_ENABLED = os.getenv("AUTH_ENABLED", "true").lower() == "true"
AUTH_HEADER = "X-User-Id"
ADMIN_ROLE = "admin"
DEFAULT_ROLE = "member"

MAX_PAGE_SIZE = 200
DEFAULT_PAGE_SIZE = 50
