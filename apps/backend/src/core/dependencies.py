from functools import lru_cache
from pathlib import Path
from src.services.reasoning_service import (
    ReasoningService,
)

from src.services.response_composer import (
    ResponseComposer,
)

from src.services.memory_extractor import (
    MemoryExtractor,
)
from src.repositories.conversation_repository import ConversationRepository
from src.repositories.in_memory_conversation_repository import (
    InMemoryConversationRepository,
)
from src.repositories.in_memory_memory_repository import (
    InMemoryMemoryRepository,
)
from src.repositories.durable_execution_repository import (
    DurableExecutionRepository,
)
from src.repositories.sqlite_durable_execution_repository import (
    SQLiteDurableExecutionRepository,
)
from src.services.knowledge_service import (
    KnowledgeService,
)

from src.services.memory_extractor import (
    MemoryExtractor,
)
from src.tools.registry import ToolRegistry
from src.tools.tool_manager import ToolManager

from src.services.agent_service import AgentService
from src.services.durable_execution_service import DurableExecutionService
from src.services.context_builder import ContextBuilder
from src.services.conversation_service import ConversationService
from src.core.config import settings
from src.services.llm_providers import FakeLLMProvider
from src.services.llm_service import LLMService
from src.services.memory_service import MemoryService
from src.services.planner_service import PlannerService
from src.services.executor_service import ExecutorService
from src.services.variable_resolver import VariableResolver
from src.services.reviewer_service import ReviewerService
from src.services.decision_service import DecisionService
from src.services.cognitive_pipeline import CognitivePipeline
from src.services.plan_parser import PlanParser
from src.services.prompt_builder import PromptBuilder
from src.services.tool_catalog import ToolCatalog
from src.services.capability_registry import CapabilityRegistry
from src.services.capability_resolver import CapabilityResolver
from src.services.permission_service import PermissionService
from src.services.document_loader import (
    DocumentLoader,
)

from src.services.chunker import (
    Chunker,
)

from src.services.embedding_service import (
    EmbeddingService,
    EmbeddingProvider,
)

from src.services.vector_store import (
    VectorStore,
    InMemoryVectorStore,
)

from src.services.retrieval_service import (
    RetrievalService,
)

from src.services.knowledge_service import (
    KnowledgeService,
)
from src.services.candidate_plan_generator import (
    CandidatePlanGenerator,
)
from src.services.plan_scorer import (
    PlanScorer,
)
from src.services.plan_validator import (
    PlanValidator,
)
class DummyEmbeddingProvider(
    EmbeddingProvider,
):

    async def embed(
        self,
        texts: list[str],
    ) -> list[list[float]]:

        vectors = []

        for text in texts:

            vector = [
                float(
                    hash(
                        word
                    ) % 1000
                )
                / 1000
                for word in text.split()[:128]
            ]

            while len(vector) < 128:
                vector.append(0.0)

            vectors.append(vector)

        return vectors

# ==========================================================
# Repositories
# ==========================================================

@lru_cache
def get_conversation_repository() -> ConversationRepository:
    return InMemoryConversationRepository()


@lru_cache
def get_memory_repository() -> InMemoryMemoryRepository:
    return InMemoryMemoryRepository()


@lru_cache
def get_durable_execution_repository() -> DurableExecutionRepository:
    return SQLiteDurableExecutionRepository(Path(settings.DURABLE_DB_PATH))

@lru_cache
def get_memory_extractor() -> MemoryExtractor:
    return MemoryExtractor(
        get_llm_service()
    )
# ==========================================================
# Core Services
# ==========================================================

@lru_cache
def get_llm_service() -> LLMService:
    if settings.LLM_FAKE_MODE:
        return LLMService(
            provider=FakeLLMProvider(),
        )

    return LLMService()


@lru_cache
def get_context_builder() -> ContextBuilder:
    return ContextBuilder()


@lru_cache
def get_memory_service() -> MemoryService:
    return MemoryService(
        get_memory_repository()
    )


@lru_cache
def get_prompt_builder() -> PromptBuilder:
    return PromptBuilder()


@lru_cache
def get_plan_parser() -> PlanParser:
    return PlanParser()


@lru_cache
def get_variable_resolver() -> VariableResolver:
    return VariableResolver()


@lru_cache
def get_reviewer_service() -> ReviewerService:
    return ReviewerService()


@lru_cache
def get_decision_service() -> DecisionService:
    return DecisionService()


@lru_cache
def get_permission_service() -> PermissionService:
    return PermissionService()

# ==========================================================
# KNOWLEDGE ENGINE
# ==========================================================

@lru_cache
def get_document_loader() -> DocumentLoader:
    return DocumentLoader()


@lru_cache
def get_chunker() -> Chunker:
    return Chunker()


@lru_cache
def get_embedding_provider() -> EmbeddingProvider:
    return DummyEmbeddingProvider()


@lru_cache
def get_embedding_service() -> EmbeddingService:
    return EmbeddingService(
        provider=get_embedding_provider(),
    )


@lru_cache
def get_vector_store() -> VectorStore:
    return VectorStore(
        InMemoryVectorStore(),
    )


@lru_cache
def get_retrieval_service() -> RetrievalService:
    return RetrievalService(
        chunker=get_chunker(),
        embedding_service=get_embedding_service(),
        vector_store=get_vector_store(),
    )


@lru_cache
def get_knowledge_service() -> KnowledgeService:
    return KnowledgeService(
        loader=get_document_loader(),
        retrieval=get_retrieval_service(),
    )
# ==========================================================
# Tooling
# ==========================================================

@lru_cache
def get_tool_manager() -> ToolManager:

    manager = ToolManager()

    ToolRegistry.register_all(manager)

    return manager


@lru_cache
def get_tool_catalog() -> ToolCatalog:
    return ToolCatalog(
        get_tool_manager()
    )


@lru_cache
def get_capability_registry() -> CapabilityRegistry:
    return CapabilityRegistry(get_tool_manager())


@lru_cache
def get_capability_resolver() -> CapabilityResolver:
    return CapabilityResolver(get_capability_registry())


# ==========================================================
# Planner / Executor
# ==========================================================

@lru_cache
def get_planner_service() -> PlannerService:
    return PlannerService(
        llm=get_llm_service(),
        parser=get_plan_parser(),
        prompt_builder=get_prompt_builder(),
        tool_catalog=get_tool_catalog(),
    )


@lru_cache
def get_executor_service() -> ExecutorService:
    return ExecutorService(
        llm=get_llm_service(),
        context_builder=get_context_builder(),
        tool_manager=get_tool_manager(),
        variable_resolver=get_variable_resolver(),
        permission_service=get_permission_service(),
        durable_repository=get_durable_execution_repository(),
    )

@lru_cache
def get_candidate_plan_generator() -> CandidatePlanGenerator:
    return CandidatePlanGenerator(
        planner=get_planner_service(),
    )


@lru_cache
def get_plan_validator() -> PlanValidator:
    return PlanValidator(
        tool_manager=get_tool_manager(),
    )


@lru_cache
def get_plan_scorer() -> PlanScorer:
    return PlanScorer()
# ==========================================================
# Cognitive Pipeline
# ==========================================================
@lru_cache
def get_cognitive_pipeline() -> CognitivePipeline:
    return CognitivePipeline(
        planner=get_planner_service(),
        executor=get_executor_service(),
        reviewer=get_reviewer_service(),
        decision=get_decision_service(),
        reasoning=get_reasoning_service(),
        response_composer=get_response_composer(),
        candidate_plan_generator=get_candidate_plan_generator(),
        plan_validator=get_plan_validator(),
        plan_scorer=get_plan_scorer(),
        capability_resolver=get_capability_resolver(),
    )
@lru_cache
def get_reasoning_service() -> ReasoningService:
    return ReasoningService(
        llm=get_llm_service(),
    )
@lru_cache
def get_response_composer() -> ResponseComposer:
    return ResponseComposer()
@lru_cache
def get_memory_extractor() -> MemoryExtractor:
    return MemoryExtractor(
        llm=get_llm_service(),
    )
# ==========================================================
# Agent
# ==========================================================

@lru_cache
def get_agent_service() -> AgentService:
    return AgentService(
        pipeline=get_cognitive_pipeline(),
        state_repository=get_cognitive_state_repository(),
        approval_service=get_approval_service(),
        memory_service=get_memory_service(),
        knowledge_service=get_knowledge_service(),
        memory_extractor=get_memory_extractor(),
        durable_execution_service=get_durable_execution_service(),
    )

# ==========================================================
# Conversation
# ==========================================================

@lru_cache
def get_conversation_service() -> ConversationService:
    return ConversationService(
        get_agent_service(),
        get_conversation_repository(),
    )
from src.repositories.cognitive_state_repository import (
    CognitiveStateRepository,
)

@lru_cache
def get_cognitive_state_repository() -> CognitiveStateRepository:
    return CognitiveStateRepository()

from src.services.approval_service import ApprovalService
@lru_cache
def get_approval_service() -> ApprovalService:
    return ApprovalService(
        tool_manager=get_tool_manager(),
        durable_repository=get_durable_execution_repository(),
        executor=get_executor_service(),
    )


@lru_cache
def get_durable_execution_service() -> DurableExecutionService:
    return DurableExecutionService(get_durable_execution_repository())




from src.services.cognitive_inspector import CognitiveInspector

@lru_cache
def get_cognitive_inspector() -> CognitiveInspector:
    return CognitiveInspector()


    from src.repositories.cognitive_state_repository import CognitiveStateRepository
from src.services.cognitive_inspector import CognitiveInspector
