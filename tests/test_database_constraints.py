import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password_async
from app.db.models import InteractiveQuestionnaire, User, UserInteractiveQuestionnaire


async def table_info(db_session: AsyncSession, table_name: str) -> dict:
    connection = await db_session.connection()
    return await connection.run_sync(
        lambda sync_conn: {
            "columns": {
                column["name"]: column
                for column in inspect(sync_conn).get_columns(table_name)
            },
            "indexes": inspect(sync_conn).get_indexes(table_name),
            "foreign_keys": inspect(sync_conn).get_foreign_keys(table_name),
            "check_constraints": inspect(sync_conn).get_check_constraints(table_name),
        }
    )


@pytest.mark.asyncio
async def test_interactive_questionnaires_schema_constraints(db_transaction_session):
    info = await table_info(db_transaction_session, "interactive_questionnaires")
    columns = info["columns"]

    assert columns["id"]["primary_key"] == 1
    assert columns["question"]["nullable"] is False
    assert columns["answer_type"]["nullable"] is False
    assert columns["answer_type"]["type"].length == 50
    assert columns["optional"]["nullable"] is False
    assert columns["answers"]["nullable"] is False
    assert columns["created_at"]["nullable"] is False
    assert columns["updated_at"]["nullable"] is False

    index_names = {index["name"] for index in info["indexes"]}
    assert "ix_interactive_questionnaires_id" in index_names
    assert "ix_interactive_questionnaires_answer_type" in index_names

    check_names = {constraint["name"] for constraint in info["check_constraints"]}
    assert "ck_interactive_questionnaires_answer_type" in check_names


@pytest.mark.asyncio
async def test_user_interactive_questionnaires_schema_constraints(db_transaction_session):
    info = await table_info(db_transaction_session, "user_interactive_questionnaires")
    columns = info["columns"]

    assert columns["id"]["primary_key"] == 1
    assert columns["user_id"]["nullable"] is False
    assert columns["questionnaire_id"]["nullable"] is False
    assert columns["user_answers"]["nullable"] is False
    assert columns["submission_date"]["nullable"] is False
    assert columns["created_at"]["nullable"] is False
    assert columns["updated_at"]["nullable"] is False

    indexes = {index["name"]: index for index in info["indexes"]}
    assert indexes["ix_user_interactive_questionnaires_user_id_questionnaire_id"]["column_names"] == [
        "user_id",
        "questionnaire_id",
    ]
    assert indexes["ix_user_interactive_questionnaires_user_id_questionnaire_id"]["unique"] == 0

    foreign_keys = {
        tuple(foreign_key["constrained_columns"]): foreign_key
        for foreign_key in info["foreign_keys"]
    }
    assert foreign_keys[("user_id",)]["referred_table"] == "users"
    assert foreign_keys[("questionnaire_id",)]["referred_table"] == "interactive_questionnaires"


@pytest.mark.asyncio
async def test_user_unique_username_constraint_raises_integrity_error(db_transaction_session):
    hashed_password = await hash_password_async("Test@12345")
    db_transaction_session.add_all(
        [
            User(username="unique@axiorapulse.com", password=hashed_password, role="user"),
            User(username="unique@axiorapulse.com", password=hashed_password, role="user"),
        ]
    )

    with pytest.raises(IntegrityError):
        await db_transaction_session.flush()


@pytest.mark.asyncio
async def test_interactive_questionnaire_question_nullability_raises_integrity_error(
    db_transaction_session,
):
    db_transaction_session.add(
        InteractiveQuestionnaire(
            question=None,
            answer_type="textarea",
            optional=False,
            answers=[],
        )
    )
    with pytest.raises(IntegrityError):
        await db_transaction_session.flush()


@pytest.mark.asyncio
async def test_interactive_questionnaire_answer_type_check_constraint_raises_integrity_error(
    db_transaction_session,
):
    db_transaction_session.add(
        InteractiveQuestionnaire(
            question="Pick one",
            answer_type="unsupported",
            optional=False,
            answers=[],
        )
    )
    with pytest.raises(IntegrityError):
        await db_transaction_session.flush()


@pytest.mark.asyncio
async def test_user_interactive_questionnaire_foreign_keys_raise_integrity_errors(
    db_transaction_session,
):
    db_transaction_session.add(
        UserInteractiveQuestionnaire(
            user_id=999999,
            questionnaire_id=999999,
            user_answers=["Answer"],
        )
    )

    with pytest.raises(IntegrityError):
        await db_transaction_session.flush()


@pytest.mark.asyncio
async def test_user_interactive_questionnaire_accepts_valid_foreign_keys(
    db_transaction_session,
):
    user = User(
        username="fk-valid@axiorapulse.com",
        password=await hash_password_async("Test@12345"),
        role="user",
        register_mfa=True,
    )
    questionnaire = InteractiveQuestionnaire(
        question="What is your market?",
        answer_type="textarea",
        optional=False,
        answers=[],
    )
    db_transaction_session.add_all([user, questionnaire])
    await db_transaction_session.flush()

    response = UserInteractiveQuestionnaire(
        user_id=user.id,
        questionnaire_id=questionnaire.id,
        user_answers=["B2B SaaS"],
    )
    db_transaction_session.add(response)
    await db_transaction_session.flush()

    assert response.id is not None
