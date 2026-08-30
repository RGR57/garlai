from enum import Enum
from typing import List

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class Priority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Complexity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Task(BaseModel):
    id: int
    title: str
    description: str

    priority: Priority
    complexity: Complexity

    estimated_duration: str

    status: TaskStatus = TaskStatus.PENDING

    dependencies: List[int] = Field(default_factory=list)


class Plan(BaseModel):
    objective: str
    tasks: List[Task]


class PlanRequest(BaseModel):
    objective: str


class PlanResponse(BaseModel):
    success: bool
    data: Plan