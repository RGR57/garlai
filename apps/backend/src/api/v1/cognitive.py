from fastapi import APIRouter, Depends, HTTPException

from src.core.dependencies import (
    get_cognitive_inspector,
    get_cognitive_state_repository,
)
from src.repositories.cognitive_state_repository import (
    CognitiveStateRepository,
)
from src.services.cognitive_inspector import (
    CognitiveInspector,
)


router = APIRouter()


@router.get(
    "/cognitive/{conversation_id}",
)
async def inspect_cognitive_state(
    conversation_id: str,
    repository: CognitiveStateRepository = Depends(
        get_cognitive_state_repository
    ),
    inspector: CognitiveInspector = Depends(
        get_cognitive_inspector
    ),
):

    state = repository.get(
        conversation_id
    )

    if state is None:

        raise HTTPException(
            status_code=404,
            detail=(
                "No cognitive state found for "
                f"conversation '{conversation_id}'."
            ),
        )

    return {
        "success": True,
        "message": (
            "Cognitive state retrieved successfully."
        ),
        "data": inspector.inspect(
            state
        ),
    }