from fastapi import APIRouter, Depends

from src.core.dependencies import (
    get_conversation_service,
)
from src.schemas.chat import (
    ChatRequest,
    ChatResponse,
)
from src.schemas.response import APIResponse
from src.services.conversation_service import (
    ConversationService,
)


router = APIRouter(
    prefix="/api/v1/chat",
    tags=["Chat"],
)


@router.post(
    "",
    response_model=APIResponse,
)
async def chat(
    request: ChatRequest,
    conversation_service: ConversationService = Depends(
        get_conversation_service
    ),
):

    print(
        ">>> GARL CHAT ROUTE ENTERED <<<",
        flush=True,
    )

    print(
        f">>> conversation_id={request.conversation_id}",
        flush=True,
    )

    print(
        f">>> message={request.message}",
        flush=True,
    )

    response = await conversation_service.chat(
        request
    )

    print(
        f">>> GARL CHAT RESPONSE={response}",
        flush=True,
    )

    return APIResponse(
        success=True,
        message="Chat completed successfully.",
        data=ChatResponse(
        response=response.response,
        artifacts=response.artifacts,
    ),
    )