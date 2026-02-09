import logging
import time

import sentry_sdk
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import AUTH_ENABLED

logger = logging.getLogger(__name__)


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if AUTH_ENABLED:
            user_id = request.headers.get("X-User-Id")
            if user_id:
                from app.database import SessionLocal
                from app.models import User
                db = SessionLocal()
                try:
                    user = db.query(User).filter(User.id == int(user_id)).first()
                    if user:
                        request.state.role = user.role
                        request.state.user_id = user.id
                    else:
                        request.state.role = None
                        request.state.user_id = None
                except Exception:
                    request.state.role = None
                    request.state.user_id = None
                finally:
                    db.close()
            else:
                request.state.role = "admin"
                request.state.user_id = None
        else:
            request.state.role = "admin"
            request.state.user_id = None

        response = await call_next(request)
        return response


class ErrorHandlingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        try:
            response = await call_next(request)
            process_time = time.time() - start_time
            response.headers["X-Process-Time"] = str(process_time)
            return response
        except Exception as exc:
            process_time = time.time() - start_time
            logger.error(
                f"Unhandled exception on {request.method} {request.url.path}: {exc}",
                exc_info=True,
            )
            with sentry_sdk.push_scope() as scope:
                scope.set_context(
                    "request",
                    {
                        "method": request.method,
                        "url": str(request.url),
                        "path": request.url.path,
                        "query_params": dict(request.query_params),
                        "process_time": process_time,
                    },
                )
                sentry_sdk.capture_exception(exc)

            return JSONResponse(
                status_code=500,
                content={
                    "detail": "Internal server error",
                    "error_type": type(exc).__name__,
                },
            )


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        logger.info(f"→ {request.method} {request.url.path}")
        response = await call_next(request)
        logger.info(f"← {request.method} {request.url.path} [{response.status_code}]")
        return response
