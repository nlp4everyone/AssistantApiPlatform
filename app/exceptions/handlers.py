from fastapi import Request
from fastapi.responses import JSONResponse
from .base_exception import AppException
from .postgres import PostgresConnectionException
from loggers import SystemLogger

async def common_exception_handler(request: Request, exc: AppException):
    return JSONResponse(
        status_code = exc.status_code,
        content = exc.response.model_dump())

async def postgres_connection_exception_handler(request: Request, exc: Exception):
    """Catch-all for asyncpg.PostgresError/socket.gaierror escaping any route handler."""
    SystemLogger.error(f"[{request.method} {request.url.path}] Postgres connection error: {exc}")
    postgres_exc = PostgresConnectionException()
    return JSONResponse(
        status_code = postgres_exc.status_code,
        content = postgres_exc.response.model_dump())