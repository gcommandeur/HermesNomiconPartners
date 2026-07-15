from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from cc_crm.api.error_handlers import register_error_handlers
from cc_crm.api.v1.router import api_router
from cc_crm.core.config import get_settings
from cc_crm.core.migrations import ensure_database_at_head


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    ensure_database_at_head()
    yield


_DOCS_ENABLED_ENVIRONMENTS = {"local", "development"}


def create_app() -> FastAPI:
    settings = get_settings()
    # /docs, /redoc, /openapi.json geben in Produktion bewusst 404 - sie
    # verraten sonst die komplette API-Struktur (Routen, Schemas, Felder)
    # oeffentlich, ohne dass das fuer den Betrieb noetig waere (siehe
    # docs/DEPLOYMENT.md, dort bisher als offener Punkt vermerkt).
    docs_enabled = settings.environment in _DOCS_ENABLED_ENVIRONMENTS
    app = FastAPI(
        title="Hermes API",
        description="Backend API for Hermes (Recruiting CRM for Commandeur Consulting)",
        version="0.1.0",
        docs_url="/docs" if docs_enabled else None,
        redoc_url="/redoc" if docs_enabled else None,
        openapi_url="/openapi.json" if docs_enabled else None,
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[str(origin).rstrip("/") for origin in settings.cors_origins],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_error_handlers(app)
    app.include_router(api_router, prefix=settings.api_prefix)
    return app


app = create_app()
