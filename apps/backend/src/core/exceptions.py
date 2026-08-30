from fastapi import Request
from fastapi.responses import JSONResponse

from src.schemas.response import APIResponse


class GARLException(Exception):

    def __init__(
        self,
        message: str,
        status_code: int = 400,
    ):
        super().__init__(message)

        self.message = message
        self.status_code = status_code


async def garl_exception_handler(
    request: Request,
    exc: GARLException,
):
    return JSONResponse(
        status_code=exc.status_code,
        content=APIResponse(
            success=False,
            message=exc.message,
            data=None,
        ).model_dump(),
    )


async def generic_exception_handler(
    request: Request,
    exc: Exception,
):
    """
    Temporary debugging handler.

    Exposes the real Python exception in the API response
    so we can diagnose the current 500 error even while
    terminal logging is not working.
    """

    error_type = type(exc).__name__

    error_message = str(exc)

    detailed_error = (
        f"{error_type}: {error_message}"
    )

    return JSONResponse(
        status_code=500,
        content=APIResponse(
            success=False,
            message=detailed_error,
            data=None,
        ).model_dump(),
    )