"""
Verification script for LLM Stream=True streaming support.
"""
import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import AsyncGenerator

# Add backend app directory to sys.path
sys.path.insert(0, str(Path(__file__).parent))

from app.agents.survey_intelligence_agent import SurveyIntelligenceAgent
from app.llm.llm_gateway import LLMGateway, LLMRequest, LLMResponse
from app.models.agent_models import AgentInput, AgentStatus

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Mock Streaming LLM Gateway to simulate word-by-word / chunk-by-chunk token emission
class MockStreamingLLMGateway(LLMGateway):

    def get_provider_name(self) -> str:
        return "mock_streaming_provider"

    def get_default_model(self) -> str:
        return "mock-llama-3"

    async def complete_stream(self, request: LLMRequest) -> AsyncGenerator[str, None]:
        payload_dict = {
            "survey_title": "Streaming B2B Survey",
            "survey_objective": "Test incremental streaming UX",
            "target_audience_summary": "SaaS Founders",
            "questions": [
                {
                    "question_text": "Do you need real-time streaming output?",
                    "question_type": "multiple_choice",
                    "target_hypothesis": "Verify streaming UX preference"
                }
            ],
            "survey_quality_score": 92.0,
            "confidence": 0.95,
            "disclaimer": "This output provides decision-support guidance only."
        }
        json_str = json.dumps(payload_dict)

        # Emit JSON payload chunk by chunk (simulating word-by-word streaming)
        chunk_size = 12
        for i in range(0, len(json_str), chunk_size):
            yield json_str[i : i + chunk_size]
            await asyncio.sleep(0.01)

    async def complete(self, request: LLMRequest) -> LLMResponse:
        chunks = []
        async for chunk in self.complete_stream(request):
            chunks.append(chunk)
        content = "".join(chunks)
        return LLMResponse(
            content=content,
            model=self.get_default_model(),
            provider=self.get_provider_name(),
            total_tokens=len(content) // 4,
            success=True,
        )


async def test_llm_token_streaming():
    logger.info("=== Testing LLM Token Streaming (stream=True) ===")
    mock_llm = MockStreamingLLMGateway()

    # 1. Test Gateway complete_stream directly
    request = LLMRequest(user_prompt="Generate survey", stream=True)
    received_chunks = []

    async for chunk in mock_llm.complete_stream(request):
        received_chunks.append(chunk)

    assert len(received_chunks) > 1, f"Expected multiple streaming chunks, got {len(received_chunks)}"
    full_reconstructed = "".join(received_chunks)
    assert "Streaming B2B Survey" in full_reconstructed
    logger.info(f"✓ Test 1 Passed: LLM Gateway streamed {len(received_chunks)} token chunks incrementally.")

    # 2. Test Agent execution with stream_callback
    agent = SurveyIntelligenceAgent(llm_gateway=mock_llm)
    agent_input = AgentInput(
        idea_title="Streaming Test Idea",
        idea_description="Testing word-by-word streaming LLM completion.",
        problem_statement="High latency waiting for long LLM completion responses.",
    )

    agent_streamed_chunks = []

    async def on_token_chunk(chunk: str):
        agent_streamed_chunks.append(chunk)

    output = await agent.run(agent_input, stream=True, stream_callback=on_token_chunk)

    assert output.status == AgentStatus.SUCCESS
    assert len(agent_streamed_chunks) > 1
    assert output.score == 92.0
    logger.info(
        f"✓ Test 2 Passed: Agent received {len(agent_streamed_chunks)} token chunks in real-time "
        f"via callback while validating output payload successfully!"
    )

    print("\n🎉 LLM STREAMING (stream=True) VERIFIED SUCCESSFULLY!")


if __name__ == "__main__":
    asyncio.run(test_llm_token_streaming())
