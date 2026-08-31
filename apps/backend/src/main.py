from fastapi import FastAPI

from src.api.v1.chat import (
    router as chat_router,
)

from src.core.exceptions import (
    GARLException,
    garl_exception_handler,
    generic_exception_handler,
)

from src.core.logging import (
    setup_logging,
)
from src.core.lifespan import lifespan


# ==========================================================
# LOGGING
# ==========================================================

setup_logging()


# ==========================================================
# APPLICATION
# ==========================================================

app = FastAPI(
    title="GARL Backend",
    version="1.0.0",
    lifespan=lifespan,
)


# ==========================================================
# EXCEPTION HANDLERS
# ==========================================================

app.add_exception_handler(
    GARLException,
    garl_exception_handler,
)

app.add_exception_handler(
    Exception,
    generic_exception_handler,
)


# ==========================================================
# ROUTERS
# ==========================================================

app.include_router(
    chat_router
)


# ==========================================================
# ROOT
# ==========================================================

@app.get("/")
async def root():
    return {
        "message": (
            "GARL Backend is running"
        )
    }
