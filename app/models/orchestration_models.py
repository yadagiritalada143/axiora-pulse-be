from pydantic import BaseModel, Field
from typing import Optional, Any
from enum import Enum
from datetime import datetime
import uuid


class ValidationVerdict(str, Enum):
    BUILD = "build"
    VALIDATE_MORE = "validate_more"
    REDUCE_SCOPE = "reduce_scope"
    PIVOT = "pivot"
    HOLD = "hold"


class WorkflowType(str, Enum):
    IDEA_VALIDATION = "idea_validation"
    SURVEY_GENERATION = "survey_generation"
    SURVEY_ANALYTICS = "survey_analytics"
    REPORT_GENERATION = "report_generation"


# ── Request Models ─────────────────────────────────────────────────────────────

class IdeaInput(BaseModel):
    """The founder's idea details submitted for validation."""

    idea_title: str = Field(..., min_length=3, description="Short name of the idea")
    idea_description: str = Field(..., min_length=10, description="Full description of the idea")
    problem_statement: str = Field(..., min_length=10, description="The core problem being solved")
    founder_evidence: Optional[str] = Field(default=None, description="Stated evidence, prior experience, or existing data")


class OrchestrationRequest(BaseModel):
    """Top-level request to start an orchestration run."""

    workspace_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Founder workspace ID",
    )
    idea_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique ID for this idea",
    )
    workflow_type: WorkflowType = Field(
        default=WorkflowType.IDEA_VALIDATION,
        description="Type of workflow to run",
    )
    idea: IdeaInput


# ── Result Models ──────────────────────────────────────────────────────────────

class ValidationResult(BaseModel):
    """Final aggregated validation result."""

    idea_id: str
    orchestration_run_id: str
    validation_score: float = Field(ge=0, le=100)
    confidence_rating: float = Field(ge=0.0, le=1.0)
    verdict: ValidationVerdict
    strengths: list[str]
    risks: list[str]
    assumptions: list[str]
    recommendations: list[str]
    agent_results: dict[str, Any]
    mentor_summary: str
    inferred_idea: Optional[IdeaInput] = None
    disclaimer: str = (
        "This is educational and decision-support guidance only. "
        "It is not legal, tax, accounting, banking, investment, loan, "
        "or professional financial advice."
    )
    created_at: datetime = Field(default_factory=datetime.utcnow)


class OrchestrationResponse(BaseModel):
    """Top-level API response from an orchestration run."""

    run_id: str
    workspace_id: str
    idea_id: str
    workflow_type: WorkflowType
    status: str                                     # success | failed
    result: Optional[ValidationResult] = None
    error: Optional[str] = None
    started_at: datetime
    completed_at: Optional[datetime] = None
