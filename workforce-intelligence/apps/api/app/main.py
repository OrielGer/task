"""FastAPI application entrypoint."""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import get_settings
from app.rate_limit import limiter
from app.routers import admin, agent, ai, analytics, auth, employees, teams


class SecureHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault(
            "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
        )
        response.headers.setdefault("Cache-Control", "no-store")
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Bucket sensitive surfaces (auth + ingestion) per client IP.
        path = request.url.path
        if path.startswith("/api/v1/auth") or path.startswith("/api/v1/agent"):
            client = request.client.host if request.client else "anon"
            key = f"{client}:{path.split('/')[4] if len(path.split('/')) > 4 else path}"
            if not limiter.allow(key):
                return JSONResponse(
                    status_code=429, content={"detail": "Rate limit exceeded"}
                )
        return await call_next(request)


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Workforce Intelligence API",
        version="0.1.0",
        description=(
            "Transparent, consent-based workforce analytics for company-owned "
            "devices. Outbound metadata ingestion only — no remote command channel."
        ),
    )

    app.add_middleware(SecureHeadersMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(auth.router)
    app.include_router(admin.router)
    app.include_router(agent.router)
    app.include_router(employees.router)
    app.include_router(teams.router)
    app.include_router(analytics.router)
    app.include_router(ai.router)

    @app.get("/health", tags=["meta"])
    def health() -> dict:
        return {"status": "ok", "ai_provider": settings.ai_provider}

    @app.get("/", tags=["meta"])
    def root() -> dict:
        return {
            "name": "Workforce Intelligence API",
            "docs": "/docs",
            "note": "Outbound metadata ingestion only; no remote command channel.",
        }

    return app


app = create_app()
