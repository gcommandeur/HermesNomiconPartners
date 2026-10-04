import threading
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from cc_crm.api.error_handlers import register_error_handlers
from cc_crm.api.v1.router import api_router
from cc_crm.core.config import get_settings
from cc_crm.core.migrations import ensure_database_at_head
from cc_crm.core.observability import RequestLoggingMiddleware, configure_logging, init_sentry


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    if settings.migrate_on_startup:
        ensure_database_at_head()
    stop = threading.Event()
    worker: threading.Thread | None = None
    if settings.embedded_worker:
        from cc_crm.infrastructure.database.session import SessionLocal
        from cc_crm.services.job_queue import run_worker_loop

        worker = threading.Thread(
            target=run_worker_loop, args=(SessionLocal, stop), name="job-worker", daemon=True
        )
        worker.start()
    try:
        yield
    finally:
        stop.set()
        if worker is not None:
            worker.join(timeout=5)


_DOCS_ENABLED_ENVIRONMENTS = {"local", "development"}

# Basis-CSP fuer eine reine JSON-API ohne eigene HTML-Seiten - das Frontend
# (Next.js, separates Deployment) laedt selbst keine externen Skripte/Fonts
# (siehe frontend/src/app/layout.tsx: kein <script>, kein next/font, keine
# fonts.googleapis.com-Referenz), insofern reicht 'self' ohne Ausnahmen.
# NUR wenn /docs aktiv ist (lokal/dev, siehe docs_enabled unten) braucht
# Swagger UI zusaetzlich cdn.jsdelivr.net (Skript/Style) - dort gilt eine
# bewusst grosszuegigere Policy, damit /docs nicht kaputtgeht; in Produktion
# ist /docs ohnehin per docs_url=None komplett abgeschaltet.
_CSP_STRICT = "default-src 'self'; frame-ancestors 'none'"
_CSP_DOCS = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' cdn.jsdelivr.net; "
    "img-src 'self' data: fastapi.tiangolo.com; "
    "frame-ancestors 'none'"
)


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level, json_logs=settings.json_logs)
    init_sentry(
        settings.sentry_dsn,
        environment=settings.environment,
        traces_sample_rate=settings.sentry_traces_sample_rate,
    )
    # /docs, /redoc, /openapi.json geben in Produktion bewusst 404 - sie
    # verraten sonst die komplette API-Struktur (Routen, Schemas, Felder)
    # oeffentlich, ohne dass das fuer den Betrieb noetig waere (siehe
    # docs/DEPLOYMENT.md, dort bisher als offener Punkt vermerkt).
    docs_enabled = settings.environment in _DOCS_ENABLED_ENVIRONMENTS
    app = FastAPI(
        title="Hermes API",
        description=f"Backend API for Hermes (Recruiting CRM for {settings.company_name})",
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

    csp = _CSP_DOCS if docs_enabled else _CSP_STRICT

    @app.middleware("http")
    async def security_headers_middleware(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """Setzt Standard-Sicherheits-Header auf jede Antwort (Punkt 5 des
        Auftrags "5 Hoch-Punkte umsetzen"). Strict-Transport-Security nur,
        wenn noch nicht gesetzt - Cloudflare setzt ihn in Produktion
        teilweise bereits selbst, ein doppelter Header waere zwar
        unschaedlich, aber unnoetig."""
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = csp
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        if "strict-transport-security" not in response.headers:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

    register_error_handlers(app)
    app.include_router(api_router, prefix=settings.api_prefix)
    # Zuletzt hinzugefuegt = aeusserste Schicht: Request-ID und Dauer umfassen
    # alles andere (inkl. CORS und Sicherheits-Header).
    app.add_middleware(RequestLoggingMiddleware)
    return app


app = create_app()
