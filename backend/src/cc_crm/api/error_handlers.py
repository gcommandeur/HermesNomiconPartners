from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from cc_crm.core.errors import (
    AIProviderError,
    AuthenticationError,
    BusinessRuleError,
    ConflictError,
    EntityNotFoundError,
    PermissionDeniedError,
    RateLimitExceededError,
)


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
