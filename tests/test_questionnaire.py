import pytest
from unittest.mock import AsyncMock, patch
from fastapi import HTTPException, status
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.models import InteractiveQuestionnaire, User, UserInteractiveQuestionnaire
from app.core.dependencies import get_current_user
from app.models.questionnaire_models import SubmitQuestionRequest, SubmitAnswersRequestItem
from app.services.questionnaire_service import questionnaire_service


def test_submit_question_request_choice_validation():
    # Textarea (not choice-based) doesn't require answers
    req = SubmitQuestionRequest(
        question="How is it?",
        answer_type="textarea",
        optional=True,
        answers=[]
    )
    assert req.question == "How is it?"
    
    # Choice-based requires at least 2 answers
    with pytest.raises(ValueError) as exc:
        SubmitQuestionRequest(
            question="Choose one?",
            answer_type="radiobuttons",
            optional=False,
            answers=["One"]
        )
    assert "Choice-based questions require at least 2 answers." in str(exc.value)


def test_submit_answers_request_item_validation():
    # Test valid item
    item = SubmitAnswersRequestItem(
        questionnaire_id=1,
        user_answers=["  Hello  ", "", "World"]
    )
    # validate_user_answers should strip whitespace and filter out empty strings
    assert item.user_answers == ["Hello", "World"]


# ──────────────────────────────────────────────────────────────────────────────
# Admin Create Question Route & Service Tests
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_question_success(client: AsyncClient, admin_user: User, db_session: AsyncSession):
    async def mock_admin_user():
        return admin_user
    
    from main import app
    app.dependency_overrides[get_current_user] = mock_admin_user

    payload = {
        "question": "What is your primary market?",
        "answer_type": "dropdown",
        "optional": False,
        "answers": ["B2B", "B2C", "Enterprise"]
    }
    
    response = await client.post("/api/v1/admin/questionnaire/create-question", json=payload)
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["question"] == "What is your primary market?"
    assert data["answer_type"] == "dropdown"
    assert data["answers"] == ["B2B", "B2C", "Enterprise"]
    assert data["optional"] is False
    assert "id" in data


@pytest.mark.asyncio
async def test_create_question_non_admin_forbidden(client: AsyncClient, normal_user: User):
    async def mock_normal_user():
        return normal_user
    
    from main import app
    app.dependency_overrides[get_current_user] = mock_normal_user

    payload = {
        "question": "What is your primary market?",
        "answer_type": "textarea",
        "optional": True,
        "answers": []
    }
    
    response = await client.post("/api/v1/admin/questionnaire/create-question", json=payload)
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json()["detail"] == "Admin privileges required."


# ──────────────────────────────────────────────────────────────────────────────
# Update Question Route & Service Tests
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_update_question_success(client: AsyncClient, admin_user: User, db_session: AsyncSession):
    question = InteractiveQuestionnaire(
        question="Original text", answer_type="textarea", optional=True, answers=[]
    )
    db_session.add(question)
    await db_session.commit()
    await db_session.refresh(question)

    async def mock_admin_user():
        return admin_user

    from main import app
    app.dependency_overrides[get_current_user] = mock_admin_user

    response = await client.put(
        f"/api/v1/admin/questionnaire/update-question/{question.id}",
        json={"question": "Updated text", "optional": False},
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["question"] == "Updated text"
    assert data["optional"] is False
    assert data["answer_type"] == "textarea"  # untouched field kept as-is


@pytest.mark.asyncio
async def test_update_question_not_found(client: AsyncClient, admin_user: User):
    async def mock_admin_user():
        return admin_user

    from main import app
    app.dependency_overrides[get_current_user] = mock_admin_user

    response = await client.put(
        "/api/v1/admin/questionnaire/update-question/999",
        json={"question": "Doesn't matter"},
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_update_question_non_admin_forbidden(client: AsyncClient, normal_user: User):
    async def mock_normal_user():
        return normal_user

    from main import app
    app.dependency_overrides[get_current_user] = mock_normal_user

    response = await client.put(
        "/api/v1/admin/questionnaire/update-question/1",
        json={"question": "Doesn't matter"},
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_update_question_updates_answer_type_and_answers(
    client: AsyncClient, admin_user: User, db_session: AsyncSession
):
    question = InteractiveQuestionnaire(
        question="Pick one", answer_type="dropdown", optional=False, answers=["A", "B"]
    )
    db_session.add(question)
    await db_session.commit()
    await db_session.refresh(question)

    async def mock_admin_user():
        return admin_user

    from main import app
    app.dependency_overrides[get_current_user] = mock_admin_user

    response = await client.put(
        f"/api/v1/admin/questionnaire/update-question/{question.id}",
        json={"answer_type": "checkboxes", "answers": ["X", "Y", "Z"]},
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["answer_type"] == "checkboxes"
    assert data["answers"] == ["X", "Y", "Z"]
    assert data["question"] == "Pick one"  # untouched field kept as-is


# ──────────────────────────────────────────────────────────────────────────────
# Delete Question Route & Service Tests
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_delete_question_success(client: AsyncClient, admin_user: User, db_session: AsyncSession):
    # Seed a question to delete
    question = InteractiveQuestionnaire(
        question="Delete me?",
        answer_type="textarea",
        optional=True,
        answers=[]
    )
    db_session.add(question)
    await db_session.commit()
    await db_session.refresh(question)

    async def mock_admin_user():
        return admin_user
    
    from main import app
    app.dependency_overrides[get_current_user] = mock_admin_user

    response = await client.delete(f"/api/v1/admin/questionnaire/delete-question/{question.id}")
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["message"] == "Questionnaire question deleted successfully."

    # Check database
    q = await db_session.get(InteractiveQuestionnaire, question.id)
    assert q is None


@pytest.mark.asyncio
async def test_delete_question_not_found(client: AsyncClient, admin_user: User):
    async def mock_admin_user():
        return admin_user
    
    from main import app
    app.dependency_overrides[get_current_user] = mock_admin_user

    response = await client.delete("/api/v1/admin/questionnaire/delete-question/999")
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json()["detail"] == "Questionnaire question not found."


@pytest.mark.asyncio
async def test_delete_question_non_admin_forbidden(client: AsyncClient, normal_user: User):
    async def mock_normal_user():
        return normal_user
    
    from main import app
    app.dependency_overrides[get_current_user] = mock_normal_user

    response = await client.delete("/api/v1/admin/questionnaire/delete-question/1")
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json()["detail"] == "Admin privileges required."


# ──────────────────────────────────────────────────────────────────────────────
# List Questions Route & Service Tests
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_questions(client: AsyncClient, normal_user: User, db_session: AsyncSession):
    # Seed questions
    q1 = InteractiveQuestionnaire(question="Q1", answer_type="textarea", optional=True, answers=[])
    q2 = InteractiveQuestionnaire(question="Q2", answer_type="dropdown", optional=False, answers=["A", "B"])
    db_session.add_all([q1, q2])
    await db_session.commit()

    async def mock_normal_user():
        return normal_user
    
    from main import app
    app.dependency_overrides[get_current_user] = mock_normal_user

    # Test user endpoint
    response = await client.get("/api/v1/questionnaire/questions")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert len(data) == 2
    assert data[0]["question"] == "Q1"
    assert data[1]["question"] == "Q2"

    # Test admin endpoint
    response_admin = await client.get("/api/v1/admin/questionnaire/questions")
    assert response_admin.status_code == status.HTTP_200_OK
    assert len(response_admin.json()) == 2


# ──────────────────────────────────────────────────────────────────────────────
# Submit Answers Route & Service Tests
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_submit_answers_empty_payload(client: AsyncClient, normal_user: User):
    async def mock_normal_user():
        return normal_user
    
    from main import app
    app.dependency_overrides[get_current_user] = mock_normal_user

    response = await client.post("/api/v1/questionnaire/submit-answers", json=[])
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json()["detail"] == "At least one questionnaire answer item is required."


@pytest.mark.asyncio
async def test_submit_answers_non_existent_question(client: AsyncClient, normal_user: User):
    async def mock_normal_user():
        return normal_user
    
    from main import app
    app.dependency_overrides[get_current_user] = mock_normal_user

    payload = [{"questionnaire_id": 999, "user_answers": ["Answer"]}]
    response = await client.post("/api/v1/questionnaire/submit-answers", json=payload)
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert "Questionnaire(s) not found" in response.json()["detail"]


@pytest.mark.asyncio
async def test_submit_answers_missing_mandatory_question(client: AsyncClient, normal_user: User, db_session: AsyncSession):
    # Seed a mandatory question and an optional question
    q_mandatory = InteractiveQuestionnaire(question="Req Q", answer_type="textarea", optional=False, answers=[])
    q_optional = InteractiveQuestionnaire(question="Opt Q", answer_type="textarea", optional=True, answers=[])
    db_session.add_all([q_mandatory, q_optional])
    await db_session.commit()
    mandatory_id = q_mandatory.id
    optional_id = q_optional.id

    async def mock_normal_user():
        return normal_user
    
    from main import app
    app.dependency_overrides[get_current_user] = mock_normal_user

    # Submit only optional question
    payload = [{"questionnaire_id": optional_id, "user_answers": ["Optional Ans"]}]
    response = await client.post("/api/v1/questionnaire/submit-answers", json=payload)
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert f"Questionnaire {mandatory_id} requires a submission entry." in response.json()["detail"]


@pytest.mark.asyncio
async def test_submit_answers_empty_answer_for_mandatory_question(client: AsyncClient, normal_user: User, db_session: AsyncSession):
    q_mandatory = InteractiveQuestionnaire(question="Req Q", answer_type="textarea", optional=False, answers=[])
    db_session.add(q_mandatory)
    await db_session.commit()
    mandatory_id = q_mandatory.id

    async def mock_normal_user():
        return normal_user
    
    from main import app
    app.dependency_overrides[get_current_user] = mock_normal_user

    # Submit empty string or empty list for mandatory question
    payload = [{"questionnaire_id": mandatory_id, "user_answers": ["   ", ""]}]
    response = await client.post("/api/v1/questionnaire/submit-answers", json=payload)
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert f"Questionnaire {mandatory_id} requires at least one non-empty answer." in response.json()["detail"]


@pytest.mark.asyncio
async def test_submit_answers_single_choice_multiple_answers(client: AsyncClient, normal_user: User, db_session: AsyncSession):
    q_choice = InteractiveQuestionnaire(
        question="Select one", 
        answer_type="radiobuttons", 
        optional=False, 
        answers=["A", "B"]
    )
    db_session.add(q_choice)
    await db_session.commit()
    choice_id = q_choice.id

    async def mock_normal_user():
        return normal_user
    
    from main import app
    app.dependency_overrides[get_current_user] = mock_normal_user

    # Submit multiple answers to single choice question
    payload = [{"questionnaire_id": choice_id, "user_answers": ["A", "B"]}]
    response = await client.post("/api/v1/questionnaire/submit-answers", json=payload)
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert f"Questionnaire {choice_id} only accepts a single choice answer." in response.json()["detail"]


@pytest.mark.asyncio
async def test_submit_answers_invalid_choice_option(client: AsyncClient, normal_user: User, db_session: AsyncSession):
    q_choice = InteractiveQuestionnaire(
        question="Select one", 
        answer_type="dropdown", 
        optional=False, 
        answers=["A", "B"]
    )
    db_session.add(q_choice)
    await db_session.commit()

    async def mock_normal_user():
        return normal_user
    
    from main import app
    app.dependency_overrides[get_current_user] = mock_normal_user

    # Submit invalid choice option
    payload = [{"questionnaire_id": q_choice.id, "user_answers": ["C"]}]
    response = await client.post("/api/v1/questionnaire/submit-answers", json=payload)
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "is not a valid option for question" in response.json()["detail"]


@pytest.mark.asyncio
async def test_submit_answers_insert_and_update_success(client: AsyncClient, normal_user: User, db_session: AsyncSession):
    q1 = InteractiveQuestionnaire(question="Q1", answer_type="textarea", optional=False, answers=[])
    q2 = InteractiveQuestionnaire(question="Q2", answer_type="checkboxes", optional=True, answers=["A", "B"])
    db_session.add_all([q1, q2])
    await db_session.commit()

    async def mock_normal_user():
        return normal_user
    
    from main import app
    app.dependency_overrides[get_current_user] = mock_normal_user

    # First submission: Creates new UserInteractiveQuestionnaire records
    payload = [
        {"questionnaire_id": q1.id, "user_answers": ["First Answer"]},
        {"questionnaire_id": q2.id, "user_answers": ["A"]}
    ]
    response = await client.post("/api/v1/questionnaire/submit-answers", json=payload)
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["message"] == "Questionnaire answers submitted successfully."

    # Verify database insertion
    res = await db_session.execute(select(UserInteractiveQuestionnaire).where(UserInteractiveQuestionnaire.user_id == normal_user.id))
    records = res.scalars().all()
    assert len(records) == 2
    record_map = {r.questionnaire_id: r for r in records}
    assert record_map[q1.id].user_answers == ["First Answer"]
    assert record_map[q2.id].user_answers == ["A"]

    # Second submission: Updates existing record for Q1
    payload_update = [
        {"questionnaire_id": q1.id, "user_answers": ["Updated Answer"]},
        {"questionnaire_id": q2.id, "user_answers": ["A", "B"]}
    ]
    response_update = await client.post("/api/v1/questionnaire/submit-answers", json=payload_update)
    assert response_update.status_code == status.HTTP_200_OK

    # Re-verify database to check updates
    res_update = await db_session.execute(select(UserInteractiveQuestionnaire).where(UserInteractiveQuestionnaire.user_id == normal_user.id))
    records_update = res_update.scalars().all()
    assert len(records_update) == 2
    record_map_update = {r.questionnaire_id: r for r in records_update}
    assert record_map_update[q1.id].user_answers == ["Updated Answer"]
    assert record_map_update[q2.id].user_answers == ["A", "B"]

    # Test the same submit-answers on admin route
    response_admin = await client.post("/api/v1/admin/questionnaire/submit-answers", json=payload_update)
    assert response_admin.status_code == status.HTTP_200_OK


# ──────────────────────────────────────────────────────────────────────────────
# Database Transaction Failure Exception Testing
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_submit_answers_db_failure(client: AsyncClient, normal_user: User, db_session: AsyncSession):
    q1 = InteractiveQuestionnaire(question="Q1", answer_type="textarea", optional=False, answers=[])
    db_session.add(q1)
    await db_session.commit()

    async def mock_normal_user():
        return normal_user
    
    from main import app
    app.dependency_overrides[get_current_user] = mock_normal_user

    # Mock db.flush to raise Exception
    payload = [{"questionnaire_id": q1.id, "user_answers": ["Answer"]}]
    
    with patch.object(db_session, "flush", side_effect=Exception("Database connection timeout")):
        with pytest.raises(Exception) as exc:
            await questionnaire_service.submit_answers(
                payload=[SubmitAnswersRequestItem(questionnaire_id=q1.id, user_answers=["Answer"])],
                current_user=normal_user,
                db=db_session
            )
        assert "Database connection timeout" in str(exc.value)


# ──────────────────────────────────────────────────────────────────────────────
# Admin Submit Answers Route Exception Handling Coverage
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_admin_submit_answers_exception(client: AsyncClient, admin_user: User):
    async def mock_admin_user():
        return admin_user
    from main import app
    app.dependency_overrides[get_current_user] = mock_admin_user
    
    # Mock the service to throw an exception to test the route's exception handler
    with patch.object(questionnaire_service, "submit_answers", side_effect=Exception("Route test exception")):
        with pytest.raises(Exception) as exc:
            await client.post(
                "/api/v1/admin/questionnaire/submit-answers", 
                json=[{"questionnaire_id": 1, "user_answers": ["A"]}]
            )
        assert "Route test exception" in str(exc.value)


# ──────────────────────────────────────────────────────────────────────────────
# Direct Service Unit Tests (Ensuring 100% Coverage of questionnaire_service.py)
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_service_list_questions(db_session: AsyncSession):
    q = InteractiveQuestionnaire(question="Test Q", answer_type="textarea", optional=True, answers=[])
    db_session.add(q)
    await db_session.commit()
    
    res = await questionnaire_service.list_questions(db_session)
    assert len(res) == 1
    assert res[0].question == "Test Q"


@pytest.mark.asyncio
async def test_service_submit_answers_empty_payload(normal_user: User, db_session: AsyncSession):
    with pytest.raises(HTTPException) as exc:
        await questionnaire_service.submit_answers(payload=[], current_user=normal_user, db=db_session)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_service_submit_answers_not_found(normal_user: User, db_session: AsyncSession):
    item = SubmitAnswersRequestItem(questionnaire_id=999, user_answers=["Ans"])
    with pytest.raises(HTTPException) as exc:
        await questionnaire_service.submit_answers(payload=[item], current_user=normal_user, db=db_session)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_service_submit_answers_missing_mandatory(normal_user: User, db_session: AsyncSession):
    q = InteractiveQuestionnaire(question="Req Q", answer_type="textarea", optional=False, answers=[])
    db_session.add(q)
    await db_session.commit()
    
    q_opt = InteractiveQuestionnaire(question="Opt Q", answer_type="textarea", optional=True, answers=[])
    db_session.add(q_opt)
    await db_session.commit()
    
    item = SubmitAnswersRequestItem(questionnaire_id=q_opt.id, user_answers=["Optional"])
    with pytest.raises(HTTPException) as exc:
        await questionnaire_service.submit_answers(payload=[item], current_user=normal_user, db=db_session)
    assert exc.value.status_code == 400
    assert "requires a submission entry" in exc.value.detail


@pytest.mark.asyncio
async def test_service_submit_answers_mandatory_empty_answer(normal_user: User, db_session: AsyncSession):
    q = InteractiveQuestionnaire(question="Req Q", answer_type="textarea", optional=False, answers=[])
    db_session.add(q)
    await db_session.commit()
    
    item = SubmitAnswersRequestItem(questionnaire_id=q.id, user_answers=["   "])
    with pytest.raises(HTTPException) as exc:
        await questionnaire_service.submit_answers(payload=[item], current_user=normal_user, db=db_session)
    assert exc.value.status_code == 400
    assert "requires at least one non-empty answer" in exc.value.detail


@pytest.mark.asyncio
async def test_service_submit_answers_choice_multiple_answers(normal_user: User, db_session: AsyncSession):
    q = InteractiveQuestionnaire(question="Choice Q", answer_type="dropdown", optional=False, answers=["A", "B"])
    db_session.add(q)
    await db_session.commit()
    
    item = SubmitAnswersRequestItem(questionnaire_id=q.id, user_answers=["A", "B"])
    with pytest.raises(HTTPException) as exc:
        await questionnaire_service.submit_answers(payload=[item], current_user=normal_user, db=db_session)
    assert exc.value.status_code == 400
    assert "only accepts a single choice answer" in exc.value.detail


@pytest.mark.asyncio
async def test_service_submit_answers_invalid_choice(normal_user: User, db_session: AsyncSession):
    q = InteractiveQuestionnaire(question="Choice Q", answer_type="dropdown", optional=False, answers=["A", "B"])
    db_session.add(q)
    await db_session.commit()
    
    item = SubmitAnswersRequestItem(questionnaire_id=q.id, user_answers=["C"])
    with pytest.raises(HTTPException) as exc:
        await questionnaire_service.submit_answers(payload=[item], current_user=normal_user, db=db_session)
    assert exc.value.status_code == 400
    assert "is not a valid option for question" in exc.value.detail


@pytest.mark.asyncio
async def test_service_submit_answers_insert_and_update(normal_user: User, db_session: AsyncSession):
    q = InteractiveQuestionnaire(question="Q", answer_type="textarea", optional=True, answers=[])
    db_session.add(q)
    await db_session.commit()
    
    item = SubmitAnswersRequestItem(questionnaire_id=q.id, user_answers=["First"])
    res = await questionnaire_service.submit_answers(payload=[item], current_user=normal_user, db=db_session)
    assert res.message == "Questionnaire answers submitted successfully."
    
    # Update
    item_update = SubmitAnswersRequestItem(questionnaire_id=q.id, user_answers=["Second"])
    res_update = await questionnaire_service.submit_answers(payload=[item_update], current_user=normal_user, db=db_session)
    assert res_update.message == "Questionnaire answers submitted successfully."


@pytest.mark.asyncio
async def test_service_create_question_non_admin(normal_user: User, db_session: AsyncSession):
    payload = SubmitQuestionRequest(question="Q", answer_type="textarea", optional=True, answers=[])
    with pytest.raises(HTTPException) as exc:
        await questionnaire_service.create_question(payload, current_user=normal_user, db=db_session)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_service_create_question_admin(admin_user: User, db_session: AsyncSession):
    payload = SubmitQuestionRequest(question="Q", answer_type="textarea", optional=True, answers=[])
    res = await questionnaire_service.create_question(payload, current_user=admin_user, db=db_session)
    assert res.question == "Q"


@pytest.mark.asyncio
async def test_service_delete_question_non_admin(normal_user: User, db_session: AsyncSession):
    with pytest.raises(HTTPException) as exc:
        await questionnaire_service.delete_question(question_id=1, current_user=normal_user, db=db_session)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_service_delete_question_not_found(admin_user: User, db_session: AsyncSession):
    with pytest.raises(HTTPException) as exc:
        await questionnaire_service.delete_question(question_id=999, current_user=admin_user, db=db_session)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_service_delete_question_admin(admin_user: User, db_session: AsyncSession):
    q = InteractiveQuestionnaire(question="Delete Q", answer_type="textarea", optional=True, answers=[])
    db_session.add(q)
    await db_session.commit()
    
    res = await questionnaire_service.delete_question(question_id=q.id, current_user=admin_user, db=db_session)
    assert res.message == "Questionnaire question deleted successfully."
