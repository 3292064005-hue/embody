from __future__ import annotations

import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from .api_common import append_log, request_id_from_request
from .errors import ApiException, ErrorCode, FailureClass, error_response
from .lifespan import context_from_request, lifespan
from .routers import calibration_router, diagnostics_router, hardware_router, health_router, system_router, task_router, vision_router, ws_router



def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in str(value or '').split(',') if item.strip()]



def _cors_settings() -> dict[str, object]:
    """Return environment-driven CORS settings.

    Environment variables:
        EMBODIED_ARM_CORS_ALLOW_ORIGINS: comma-separated explicit origin list.
        EMBODIED_ARM_CORS_ALLOW_CREDENTIALS: ``true`` / ``false``.
        EMBODIED_ARM_CORS_ALLOW_METHODS: comma-separated method list.
        EMBODIED_ARM_CORS_ALLOW_HEADERS: comma-separated header list.

    Returns:
        dict[str, object]: Keyword arguments for ``CORSMiddleware``.
    """
    allow_credentials = os.environ.get('EMBODIED_ARM_CORS_ALLOW_CREDENTIALS', 'true').lower() == 'true'
    allow_origins = _split_csv(os.environ.get('EMBODIED_ARM_CORS_ALLOW_ORIGINS', 'http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173,http://127.0.0.1:4173'))
    allow_methods = _split_csv(os.environ.get('EMBODIED_ARM_CORS_ALLOW_METHODS', 'GET,POST,PUT,DELETE,OPTIONS')) or ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS']
    allow_headers = _split_csv(os.environ.get('EMBODIED_ARM_CORS_ALLOW_HEADERS', 'Authorization,Content-Type,X-Operator-Role,X-Request-ID')) or ['Authorization', 'Content-Type', 'X-Operator-Role', 'X-Request-ID']
    if allow_credentials and '*' in allow_origins:
        raise RuntimeError('credentialed CORS requires explicit EMBODIED_ARM_CORS_ALLOW_ORIGINS entries')
    return {
        'allow_origins': allow_origins,
        'allow_credentials': allow_credentials,
        'allow_methods': allow_methods,
        'allow_headers': allow_headers,
    }



def create_app() -> FastAPI:
    """Create the gateway FastAPI application.

    Returns:
        Configured FastAPI application with lifespan hooks, routers and exception handlers.
    """
    app = FastAPI(title='Embodied Arm HMI Gateway', version='2.3.0', lifespan=lifespan)
    app.add_middleware(CORSMiddleware, **_cors_settings())

    for router in (
        health_router,
        system_router,
        task_router,
        vision_router,
        calibration_router,
        hardware_router,
        diagnostics_router,
        ws_router,
    ):
        app.include_router(router)

    @app.exception_handler(ApiException)
    async def api_exception_handler(request: Request, exc: ApiException):
        return error_response(
            exc.status_code,
            str(exc.detail),
            request_id_from_request(request),
            code=exc.error_code,
            error=exc.error,
            failure_class=exc.failure_class,
            operator_actionable=exc.operator_actionable,
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception):
        """Return a sanitized internal-error envelope for unexpected exceptions.

        Args:
            request: Incoming FastAPI request.
            exc: Unexpected exception instance.

        Returns:
            Stable JSON error envelope that does not leak raw internal exception text.

        Raises:
            Does not raise. Logging failures are suppressed so the sanitized error
            response remains stable.
        """
        try:
            ctx = context_from_request(request)
            append_log(
                'error',
                'gateway.server',
                'server.unhandled_exception',
                'unhandled gateway exception',
                request_id=request_id_from_request(request),
                payload={
                    'path': str(getattr(getattr(request, 'url', None), 'path', '')),
                    'method': getattr(request, 'method', ''),
                    'exceptionType': exc.__class__.__name__,
                },
                ctx=ctx,
            )
        except Exception:
            pass
        return error_response(
            500,
            'internal server error',
            request_id_from_request(request),
            error=ErrorCode.INTERNAL_ERROR,
            failure_class=FailureClass.INTERNAL_BUG,
            operator_actionable=False,
        )

    return app


app = create_app()
