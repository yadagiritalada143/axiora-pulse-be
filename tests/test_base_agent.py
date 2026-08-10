import json
from unittest.mock import patch

import pytest

from app.agents.base_agent import BaseAgent
from app.llm.llm_gateway import LLMGateway, LLMRequest, LLMResponse
from app.models.agent_models import AgentInput, AgentStatus
from app.skills.skill_registry import Skill


# test doubles

class DummyAgent(BaseAgent):
    """Minimal concrete BaseAgent subclass for exercising the shared run() lifecycle."""
    agent_name = "dummy_agent"
    skill_name = "dummy_skill"

    def _build_prompt(self, agent_input: AgentInput) -> str:
        return f"Analyze: {agent_input.idea_title}"

    def _parse_output(self, raw_content: str) -> dict:
        return json.loads(raw_content)

    def _extract_score(self, parsed_output: dict) -> float:
        return parsed_output["score"]


class NoSkillAgent(BaseAgent):
    """skill_name left at the abstract base default ("") — _load_skill() no-ops."""
    agent_name = "no_skill_agent"

    def _build_prompt(self, agent_input: AgentInput) -> str:
        return "prompt"

    def _parse_output(self, raw_content: str) -> dict:
        return {}

    def _extract_score(self, parsed_output: dict) -> float:
        return 0.0


class BadPromptAgent(DummyAgent):
    def _build_prompt(self, agent_input: AgentInput) -> str:
        raise RuntimeError("template rendering exploded")


class BadParseAgent(DummyAgent):
    def _parse_output(self, raw_content: str) -> dict:
        raise KeyError("not json-decode-error, a different failure")


class FakeLLMGateway(LLMGateway):
    def __init__(self, response: LLMResponse | None = None, raise_exc: Exception | None = None):
        self._response = response
        self._raise_exc = raise_exc

    async def complete(self, request: LLMRequest) -> LLMResponse:
        if self._raise_exc:
            raise self._raise_exc
        return self._response

    async def complete_stream(self, request: LLMRequest):
        content = self._response.content if self._response else ""
        for chunk in content:
            yield chunk

    def get_provider_name(self) -> str:
        return "fake"

    def get_default_model(self) -> str:
        return "fake-model"


def make_agent_input(**overrides) -> AgentInput:
    base = dict(
        idea_title="Invoice Tracker",
        idea_description="Helps freelancers track unpaid invoices automatically.",
        problem_statement="Freelancers lose track of unpaid invoices.",
    )
    base.update(overrides)
    return AgentInput(**base)


@pytest.fixture
def fake_skill() -> Skill:
    return Skill({"name": "dummy_skill", "purpose": "Testing agent lifecycle", "prompt_template": "template"})


def build_agent(agent_cls, llm_gateway, skill):
    with patch("app.agents.base_agent.skill_registry.get", return_value=skill):
        return agent_cls(llm_gateway)


# skill loading

def test_load_skill_raises_when_skill_not_found():
    with patch("app.agents.base_agent.skill_registry.get", return_value=None):
        with pytest.raises(ValueError, match="not found in registry"):
            DummyAgent(FakeLLMGateway())


def test_load_skill_noop_when_skill_name_empty():
    agent = NoSkillAgent(FakeLLMGateway())
    assert agent.skill is None


# run() — control flow

@pytest.mark.asyncio
async def test_run_fails_when_skill_not_loaded():
    agent = NoSkillAgent(FakeLLMGateway())
    output = await agent.run(make_agent_input())

    assert output.status == AgentStatus.FAILED
    assert "Skill not loaded" in output.error


@pytest.mark.asyncio
async def test_run_fails_when_build_prompt_raises(fake_skill):
    agent = build_agent(BadPromptAgent, FakeLLMGateway(), fake_skill)
    output = await agent.run(make_agent_input())

    assert output.status == AgentStatus.FAILED
    assert "Prompt build error" in output.error


@pytest.mark.asyncio
async def test_run_fails_when_llm_gateway_raises(fake_skill):
    agent = build_agent(DummyAgent, FakeLLMGateway(raise_exc=RuntimeError("network down")), fake_skill)
    output = await agent.run(make_agent_input())

    assert output.status == AgentStatus.FAILED
    assert output.error == "LLM call failed unexpectedly."


@pytest.mark.asyncio
async def test_run_fails_when_llm_response_unsuccessful(fake_skill):
    response = LLMResponse(
        content="", model="fake-model", provider="fake", success=False, error="Rate limited",
        tokens_input=10, tokens_output=0,
    )
    agent = build_agent(DummyAgent, FakeLLMGateway(response=response), fake_skill)
    output = await agent.run(make_agent_input())

    assert output.status == AgentStatus.FAILED
    assert output.error == "Rate limited"
    assert output.model_used == "fake-model"
    assert output.tokens_input == 10


@pytest.mark.asyncio
async def test_run_fails_on_json_decode_error(fake_skill):
    response = LLMResponse(content="not valid json {{{", model="fake-model", provider="fake", success=True)
    agent = build_agent(DummyAgent, FakeLLMGateway(response=response), fake_skill)
    output = await agent.run(make_agent_input())

    assert output.status == AgentStatus.FAILED
    assert output.error == "Could not parse agent response. Please retry."


@pytest.mark.asyncio
async def test_run_fails_on_generic_parse_error(fake_skill):
    response = LLMResponse(content='{"score": 90}', model="fake-model", provider="fake", success=True)
    agent = build_agent(BadParseAgent, FakeLLMGateway(response=response), fake_skill)
    output = await agent.run(make_agent_input())

    assert output.status == AgentStatus.FAILED
    assert output.error == "Output parsing failed."


@pytest.mark.asyncio
async def test_run_success_path_returns_score_and_confidence(fake_skill):
    response = LLMResponse(
        content='{"score": 85, "confidence": 0.9}',
        model="fake-model", provider="fake", success=True,
        tokens_input=100, tokens_output=50,
    )
    agent = build_agent(DummyAgent, FakeLLMGateway(response=response), fake_skill)
    output = await agent.run(make_agent_input())

    assert output.status == AgentStatus.SUCCESS
    assert output.score == 85.0
    assert output.confidence == 0.9
    assert output.data == {"score": 85, "confidence": 0.9}
    assert output.model_used == "fake-model"
    assert output.tokens_input == 100
    assert output.tokens_output == 50


@pytest.mark.asyncio
async def test_run_clamps_score_above_100(fake_skill):
    response = LLMResponse(content='{"score": 500}', model="m", provider="fake", success=True)
    agent = build_agent(DummyAgent, FakeLLMGateway(response=response), fake_skill)
    output = await agent.run(make_agent_input())
    assert output.score == 100.0


@pytest.mark.asyncio
async def test_run_clamps_score_below_0(fake_skill):
    response = LLMResponse(content='{"score": -50}', model="m", provider="fake", success=True)
    agent = build_agent(DummyAgent, FakeLLMGateway(response=response), fake_skill)
    output = await agent.run(make_agent_input())
    assert output.score == 0.0


@pytest.mark.asyncio
async def test_run_score_extraction_failure_defaults_to_50(fake_skill):
    response = LLMResponse(content='{"no_score_field": true}', model="m", provider="fake", success=True)
    agent = build_agent(DummyAgent, FakeLLMGateway(response=response), fake_skill)
    output = await agent.run(make_agent_input())

    assert output.status == AgentStatus.SUCCESS  # score extraction failure doesn't fail the whole run
    assert output.score == 50.0


@pytest.mark.asyncio
async def test_run_confidence_defaults_when_missing(fake_skill):
    response = LLMResponse(content='{"score": 70}', model="m", provider="fake", success=True)
    agent = build_agent(DummyAgent, FakeLLMGateway(response=response), fake_skill)
    output = await agent.run(make_agent_input())
    assert output.confidence == 0.5


@pytest.mark.asyncio
async def test_run_confidence_clamped_to_range(fake_skill):
    response = LLMResponse(content='{"score": 70, "confidence": 5.0}', model="m", provider="fake", success=True)
    agent = build_agent(DummyAgent, FakeLLMGateway(response=response), fake_skill)
    output = await agent.run(make_agent_input())
    assert output.confidence == 1.0


@pytest.mark.asyncio
async def test_run_streaming_accumulates_chunks_via_callback(fake_skill):
    response = LLMResponse(content='{"score": 60}', model="m", provider="fake", success=True)
    agent = build_agent(DummyAgent, FakeLLMGateway(response=response), fake_skill)

    received_chunks = []

    async def _callback(chunk: str) -> None:
        received_chunks.append(chunk)

    output = await agent.run(make_agent_input(), stream_callback=_callback)

    assert output.status == AgentStatus.SUCCESS
    assert output.score == 60.0
    assert "".join(received_chunks) == '{"score": 60}'
