from pydantic import BaseModel

from src.models.artifact import Artifact


class ChatRequest(BaseModel):

    conversation_id: str

    message: str


class ChatResponse(BaseModel):

    response: str

    artifacts: list[Artifact] = []