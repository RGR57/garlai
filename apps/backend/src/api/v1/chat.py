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

    response = await conversation_service.chat(
        request
    )

    return APIResponse(
        success=True,
        message="Chat completed successfully.",
        data=ChatResponse(
            response=response.response,
            artifacts=response.artifacts,
            execution_id=response.execution_id,
            execution_status=response.execution_status,
            pending_approval_id=response.pending_approval_id,
        ),
    )
