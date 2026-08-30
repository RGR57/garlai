from src.models.conversation import ConversationMessage

from src.repositories.conversation_repository import (
    ConversationRepository,
)

from src.schemas.chat import ChatRequest

from src.services.agent_service import AgentService

from src.utils.logger import logger


class ConversationService:

    def __init__(
        self,
        agent: AgentService,
        repository: ConversationRepository,
    ):
        self.agent = agent
        self.repository = repository

    async def chat(
        self,
        request: ChatRequest,
    ) -> str:

        logger.info(
            "Incoming chat request"
        )

        logger.info(
            f"Conversation ID: "
            f"{request.conversation_id}"
        )

        logger.info(
            f"Prompt: {request.message}"
        )

        # ======================================================
        # STORE USER MESSAGE
        # ======================================================

        await self.repository.add_message(
            request.conversation_id,
            ConversationMessage(
                role="user",
                content=request.message,
            ),
        )

        # ======================================================
        # RETRIEVE CONVERSATION
        # ======================================================

        messages = await self.repository.get_messages(
            request.conversation_id
        )

        logger.info(
            "Retrieved Messages:"
        )

        for msg in messages:

            logger.info(
                f"{msg.role}: {msg.content}"
            )

        # ======================================================
        # AGENT
        # ======================================================

        agent_response = await self.agent.respond(
        conversation_id=request.conversation_id,
        messages=messages,
    )

        # ======================================================
        # STORE ASSISTANT RESPONSE
        # ======================================================

        await self.repository.add_message(
            request.conversation_id,
            ConversationMessage(
                role="assistant",
                content=agent_response.response,
            ),
        )

        logger.info(
    "LLM response generated successfully"
        )

        return agent_response