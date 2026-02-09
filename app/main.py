import logging

import sentry_sdk
from fastapi import FastAPI

from app.config import APP_NAME, APP_VERSION, SENTRY_DSN, SENTRY_ENVIRONMENT, SENTRY_TRACES_SAMPLE_RATE
from app.middleware import ErrorHandlingMiddleware, RequestLoggingMiddleware, AuthMiddleware
from app.routers import organizations, tasks, users, comments

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

if SENTRY_DSN:
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        environment=SENTRY_ENVIRONMENT,
        traces_sample_rate=SENTRY_TRACES_SAMPLE_RATE,
        send_default_pii=True,
    )

app = FastAPI(title=APP_NAME, version=APP_VERSION)

app.add_middleware(ErrorHandlingMiddleware)
app.add_middleware(AuthMiddleware)
app.add_middleware(RequestLoggingMiddleware)

app.include_router(users.router, prefix="/api/v1")
app.include_router(organizations.router, prefix="/api/v1")
app.include_router(tasks.router, prefix="/api/v1")
app.include_router(comments.router, prefix="/api/v1")


@app.get("/")
def root():
    return {"name": APP_NAME, "version": APP_VERSION, "status": "running"}


@app.get("/health")
def health_check():
    return {"status": "healthy"}
