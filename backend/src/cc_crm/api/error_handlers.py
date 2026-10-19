import logging

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from cc_crm.core.errors import (
    AIProviderError,
    AuthenticationError,
    BusinessRuleError,
    ConflictError,
    ConsentNotGrantedError,
    EntityNotFoundError,
    OverlapConflictError,
    PermissionDeniedError,
    RateLimitExceededError,
)

logger = logging.getLogger("cc_crm.errors")


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(EntityNotFoundError)
    async def not_found_handler(
        _request: Request,
        exception: EntityNotFoundError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": str(exception)},
        )

    @app.exception_handler(OverlapConflictError)  # NOMICON: Überlassung, mit Liste der Treffer
    async def overlap_conflict_handler(
        _request: Request,
        exception: OverlapConflictError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"detail": str(exception), "overlaps": exception.overlaps},
        )

    @app.exception_handler(ConflictError)
    async def conflict_handler(
        _request: Request,
        exception: ConflictError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"detail": str(exception)},
        )

    @app.exception_handler(BusinessRuleError)
    async def business_rule_handler(
        _request: Request,
        exception: BusinessRuleError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={"detail": str(exception)},
        )

    @app.exception_handler(AuthenticationError)
    async def authentication_handler(
        _request: Request,
        exception: AuthenticationError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"detail": str(exception)},
            headers={"WWW-Authenticate": "Bearer"},
        )

    @app.exception_handler(PermissionDeniedError)
    async def permission_denied_handler(
        _request: Request,
        exception: PermissionDeniedError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"detail": str(exception)},
        )

    @app.exception_handler(ConsentNotGrantedError)
    async def consent_not_granted_handler(
        _request: Request,
        exception: ConsentNotGrantedError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"detail": str(exception)},
        )

    @app.exception_handler(RateLimitExceededError)
    async def rate_limit_handler(
        _request: Request,
        exception: RateLimitExceededError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={"detail": str(exception)},
        )

    @app.exception_handler(AIProviderError)
    async def ai_provider_handler(
        _request: Request,
        exception: AIProviderError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content={"detail": str(exception)},
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request,
        exception: Exception,
    ) -> JSONResponse:
        # Ohne diesen Catch-All faellt eine unerwartete Exception auf
        # Starlettes eingebauten Default zurueck - ein reiner Plain-Text-Body
        # "Internal Server Error" ohne jede weitere Information, UND (in
        # diesem Projekt beobachtet) ohne verlaesslich sichtbaren Traceback
        # in den DigitalOcean-Runtime-Logs. Explizites `logger.exception()`
        # hier stellt sicher, dass der volle Traceback in jedem Fall geloggt
        # wird, unabhaengig davon, ob/wie der ASGI-Server selbst unbehandelte
        # Exceptions protokolliert - und die Antwort an den Client bleibt
        # trotzdem die gewohnte knappe JSON-Form statt eines rohen
        # Plain-Text-500ers.
        logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Ein unerwarteter Fehler ist aufgetreten."},
        )
