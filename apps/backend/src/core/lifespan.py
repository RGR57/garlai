from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.core.logging import setup_logging


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()

    print("GARL Backend Started")

    yield

    print("GARL Backend Stopped")