"""SQLAlchemy ORM models for users, workspace, agents, and orchestration system."""
from datetime import datetime
import uuid


from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, JSON

from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    """Persisted user record — never expose hashed password or raw OTP in API responses."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, index=True
    )
    role: Mapped[str] = mapped_column(
        String(20), nullable=False, default="user"
    )
    username: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    display_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    password: Mapped[str] = mapped_column(
        String(512), nullable=False
    )
    register_otp: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    register_otp_expiry: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    register_mfa: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    register_otp_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    forgot_password_otp: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    forgot_password_otp_expiry: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    password_changed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    login_otp: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    login_otp_expiry: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} username={self.username!r} role={self.role!r}>"


class RefreshSession(Base):
    """A server-side record for a rotating refresh token session."""

    __tablename__ = "refresh_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )


class AuthActions(Base):
    """Per-user auth-gate flags returned on every successful regular-user login.

    payment              – True  → user has completed payment (default: True)
    interactive_questions – False → user has not yet answered onboarding questions (default: False)
    """

    __tablename__ = "auth_actions"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, index=True
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, unique=True, index=True
    )
    payment: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    interactive_questions: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def __repr__(self) -> str:
        return (
            f"<AuthActions user_id={self.user_id} "
            f"payment={self.payment} interactive_questions={self.interactive_questions}>"
        )


class InteractiveQuestionnaire(Base):
    """Admin-defined question template for interactive questionnaires."""

    __tablename__ = "interactive_questionnaires"
    __table_args__ = (
        CheckConstraint(
            "answer_type IN ('textarea', 'radiobuttons', 'checkboxes', 'dropdown')",
            name="ck_interactive_questionnaires_answer_type",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, index=True
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer_type: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )
    optional: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    answers: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def __repr__(self) -> str:
        return f"<InteractiveQuestionnaire id={self.id} answer_type={self.answer_type!r}>"


class UserInteractiveQuestionnaire(Base):
    """Stores a user's responses to a questionnaire template."""

    __tablename__ = "user_interactive_questionnaires"
    __table_args__ = (
        Index(
            "ix_user_interactive_questionnaires_user_id_questionnaire_id",
            "user_id",
            "questionnaire_id",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, index=True
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    questionnaire_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("interactive_questionnaires.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_answers: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list
    )
    submission_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def __repr__(self) -> str:
        return f"<UserInteractiveQuestionnaire id={self.id} user_id={self.user_id} questionnaire_id={self.questionnaire_id}>"


class Workspace(Base):
    """
    Persisted Workspace record — scoped to a user.
    Owns workspace metadata, mentor conversation state, extracted idea details, and validation reports.
    """

    __tablename__ = "workspaces"
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_workspaces_user_id_name"),
    )

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, index=True
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(
        String(255), nullable=False
    )
    description: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )
    state: Mapped[str] = mapped_column(
        String(50), nullable=False, default="GATHERING_INFO"
    )
    idea: Mapped[dict] = mapped_column(
        JSON, nullable=False, default=dict
    )
    conversation_history: Mapped[list] = mapped_column(
        JSON, nullable=False, default=list
    )
    validation_result: Mapped[dict | None] = mapped_column(
        JSON, nullable=True
    )
    is_delete: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def __repr__(self) -> str:
        return f"<Workspace id={self.id} name={self.name!r} user_id={self.user_id} state={self.state!r} is_delete={self.is_delete}>"


class WorkspaceAttachment(Base):
    """
    Persisted record of a file uploaded by a user into a workspace.
    Stores the S3 key and public URL for images, PDFs, and documents.
    Files are stored in axiora-assets under:
      Assets/users/{user_id}/workspaces/{workspace_id}/{type}/{uuid}_{filename}
    """

    __tablename__ = "workspace_attachments"
    __table_args__ = (
        Index("ix_workspace_attachments_workspace_id", "workspace_id"),
        Index("ix_workspace_attachments_user_id", "user_id"),
        CheckConstraint(
            "file_type IN ('image', 'pdf', 'doc')",
            name="ck_workspace_attachments_file_type",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, index=True
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    workspace_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    file_name: Mapped[str] = mapped_column(String(512), nullable=False)
    file_type: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True
    )  # 'image' | 'pdf' | 'doc'
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False, default="application/octet-stream")
    s3_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    file_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    file_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def __repr__(self) -> str:
        return (
            f"<WorkspaceAttachment id={self.id} file_name={self.file_name!r} "
            f"file_type={self.file_type!r} workspace_id={self.workspace_id}>"
        )


class Survey(Base):
    """Persisted survey record — owns a set of questions scoped to a user's workspace."""

    __tablename__ = "surveys"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, index=True
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    workspace_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    survey_link: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    questions: Mapped[list] = mapped_column(
        JSON, nullable=False, default=list
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def __repr__(self) -> str:
        return f"<Survey id={self.id} user_id={self.user_id} workspace_id={self.workspace_id}>"


class PublicSurveyResponse(Base):
    """Stores external user responses for a shareable public survey."""

    __tablename__ = "public_survey_responses"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, index=True
    )
    survey_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("surveys.id", ondelete="CASCADE"), nullable=False, index=True
    )
    respondent_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    answers: Mapped[list] = mapped_column(
        JSON, nullable=False, default=list
    )
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    def __repr__(self) -> str:
        return f"<PublicSurveyResponse id={self.id} survey_id={self.survey_id}>"



# ── Section 11: Core Orchestration Data Models (8 Tables) ─────────────────────

class AgentDefinition(Base):
    """Stores metadata about each agent."""
    __tablename__ = "agent_definitions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[str] = mapped_column(String(20), nullable=False, default="1.0")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    skill_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    default_model: Mapped[str] = mapped_column(String(100), nullable=False, default="gemini-1.5-flash")
    output_schema: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)


class SkillLibrary(Base):
    """Stores reusable skills."""
    __tablename__ = "skills_library"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    skill_name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_template: Mapped[str] = mapped_column(Text, nullable=False)
    input_schema: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    output_schema: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    guardrails: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    version: Mapped[str] = mapped_column(String(20), nullable=False, default="1.0")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")


class OrchestrationRun(Base):
    """Stores each full orchestration run."""
    __tablename__ = "orchestration_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    workspace_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    idea_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    run_type: Mapped[str] = mapped_column(String(50), nullable=False, default="idea_validation")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    final_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    final_verdict: Mapped[str | None] = mapped_column(String(50), nullable=True)


class OrchestrationStep(Base):
    """Stores each step in an orchestration run."""
    __tablename__ = "orchestration_steps"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    orchestration_run_id: Mapped[str] = mapped_column(String(36), ForeignKey("orchestration_runs.id"), nullable=False, index=True)
    step_name: Mapped[str] = mapped_column(String(100), nullable=False)
    agent_name: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class AgentRun(Base):
    """Stores each agent execution details."""
    __tablename__ = "agent_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    orchestration_run_id: Mapped[str] = mapped_column(String(36), ForeignKey("orchestration_runs.id"), nullable=False, index=True)
    agent_id: Mapped[str] = mapped_column(String(100), nullable=False)
    input_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    output_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="success")
    model_used: Mapped[str | None] = mapped_column(String(100), nullable=True)
    token_input: Mapped[int] = mapped_column(Integer, default=0)
    token_output: Mapped[int] = mapped_column(Integer, default=0)
    cost_estimate: Mapped[float] = mapped_column(Float, default=0.0)


class MCPToolCallRecord(Base):
    """Stores tool usage requested via MCP."""
    __tablename__ = "mcp_tool_calls"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    orchestration_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    agent_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    tool_name: Mapped[str] = mapped_column(String(100), nullable=False)
    input_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    output_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="success")
    execution_time_ms: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class LLMUsageLogRecord(Base):
    """Stores LLM token usage and cost metrics."""
    __tablename__ = "llm_usage_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost: Mapped[float] = mapped_column(Float, default=0.0)
    request_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    response_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="success")


class ValidationResultRecord(Base):
    """Stores final validation result per idea & orchestration run."""
    __tablename__ = "validation_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    idea_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    orchestration_run_id: Mapped[str] = mapped_column(String(36), ForeignKey("orchestration_runs.id"), nullable=False, index=True)
    validation_score: Mapped[float] = mapped_column(Float, nullable=False)
    confidence_rating: Mapped[float] = mapped_column(Float, nullable=False)
    verdict: Mapped[str] = mapped_column(String(50), nullable=False)
    strengths: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    risks: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    assumptions: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    recommendations: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
