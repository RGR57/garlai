from fastapi import APIRouter

from src.api.routes import planner

api_router = APIRouter()

api_router.include_router(planner.router)

from src.api.v1.cognitive import router as cognitive_router

router.include_router(
    cognitive_router,
    tags=["Cognitive Debug"],
)