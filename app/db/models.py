"""
app/db/models.py
────────────────────────────────────────────────────────────────────────────────
SQLAlchemy ORM model for the User table.

Column mapping (spec → SQLAlchemy):
  id                → Integer PK, autoincrement starting at 1
  role              → String, default "user"
  username          → String, unique, not null  (email or phone)
  password          → String, not null          (PBKDF2 hashed)
  register_otp      → Integer, nullable         (6-digit OTP)
  register_otp_expiry → DateTime(timezone=True), nullable
  register_mfa      → Boolean, default False    (True after OTP verified)
"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, JSON
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


class MentorSessionORM(Base):
    """Persisted AI Mentor session record."""

    __tablename__ = "mentor_sessions"

    session_id: Mapped[str] = mapped_column(
        String(255), primary_key=True, index=True
    )
    workspace_id: Mapped[str] = mapped_column(
        String(255), nullable=False
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

    def __repr__(self) -> str:
        return f"<MentorSessionORM session_id={self.session_id!r} state={self.state!r}>"

