from pydantic import BaseModel

from src.models.artifact import Artifact


class ChatRequest(BaseModel):

    conversation_id: str

    message: str

    execution_id: str | None = None

    approval_id: str | None = None


class ChatResponse(BaseModel):

    response: str

    artifacts: list[Artifact] = []

    execution_id: str | None = None

    execution_status: str | None = None

    pending_approval_id: str | None = None
