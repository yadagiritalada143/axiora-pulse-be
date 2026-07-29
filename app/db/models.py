"""SQLAlchemy ORM models for users, questionnaire templates, and workspace data."""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, JSON
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


class InteractiveQuestionnaire(Base):
    """Admin-defined question template for interactive questionnaires."""

    __tablename__ = "interactive_questionnaires"

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
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def __repr__(self) -> str:
        return f"<Workspace id={self.id} name={self.name!r} user_id={self.user_id} state={self.state!r}>"


# Compatibility aliases
WorkspaceStateORM = Workspace
MentorSessionORM = Workspace
