from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.core.logging import setup_logging
from src.core.dependencies import get_durable_execution_repository


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    await get_durable_execution_repository().initialize()

    yield
