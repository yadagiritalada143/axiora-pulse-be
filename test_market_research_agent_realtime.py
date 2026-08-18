"""
Live Real-Time Web Search & MarketResearchAgent Test Script
──────────────────────────────────────────────────────────────────────────────
Runs MarketResearchAgent with OpenAI Provider (gpt-5.4-mini) and verifies real-time
DuckDuckGo web search tool calls in log outputs.
"""
import asyncio
import json
import logging
import sys
from pathlib import Path

# Add backend directory to sys.path
sys.path.insert(0, str(Path(__file__).parent))

from app.llm.providers.openai_provider import OpenAIProvider
from app.agents.market_research_agent import MarketResearchAgent
from app.models.agent_models import AgentInput

# Set up clean logging to display real-time tool execution logs
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("TestMarketResearch")


async def run_live_market_research_test():
    print("=" * 80)
    print("🚀 Axiora Pulse - Live MarketResearchAgent Real-Time Web Search Test")
    print("=" * 80)

    # 1. Initialize OpenAI Gateway
    try:
        gateway = OpenAIProvider()
        print(f"[✓] Initialized OpenAI Gateway (Model: {gateway.get_default_model()})")
    except Exception as e:
        print(f"[❌] Failed to initialize OpenAIProvider: {e}")
        return

    # 2. Instantiate MarketResearchAgent
    agent = MarketResearchAgent(llm_gateway=gateway)
    print(f"[✓] Initialized Agent: '{agent.agent_name}' with skill '{agent.skill_name}'")
    print("-" * 80)

    # 3. Define Live Test Startup Idea
    test_input = AgentInput(
        idea_title="PulseVoice - AI Voice Agent for B2B Customer Feedback Surveys",
        idea_description=(
            "An AI-powered voice agent platform that conducts 2-minute phone call interviews "
            "with recent SaaS customers to gather qualitative churn feedback, NPS scores, and pain points."
        ),
        problem_statement=(
            "B2B SaaS companies struggle with extremely low email survey response rates (< 3%), "
            "leaving product managers with little to no qualitative feedback on churn causes."
        ),
        industry="B2B SaaS / Market Research Technology",
        geography="North America & Europe",
        business_type="B2B SaaS",
        additional_context={
            "falsifiable_problem_sentence": (
                "B2B SaaS companies lose over 15% of ARR annually to preventable churn because email surveys fail to capture real customer complaints."
            ),
            "who_and_frequency": "Head of Product & Customer Success Managers at 50-500 employee SaaS companies, weekly.",
        },
    )

    print(f"\n📋 Input Startup Idea:")
    print(f"   Title       : {test_input.idea_title}")
    print(f"   Industry    : {test_input.industry}")
    print(f"   Problem     : {test_input.problem_statement}")
    print("\n" + "=" * 80)
    print("🔄 Running MarketResearchAgent Execution (Watching for DuckDuckGo Tool Calls)...")
    print("=" * 80 + "\n")

    # 4. Execute Agent Run
    output = await agent.run(test_input)

    print("\n" + "=" * 80)
    print("📊 Execution Summary & Results")
    print("=" * 80)
    print(f"   Status             : {output.status}")
    print(f"   Score              : {output.score} / 100")
    print(f"   Confidence         : {output.confidence}")
    print(f"   Model Used         : {output.model_used}")
    print(f"   Tokens (In / Out)  : {output.tokens_input} / {output.tokens_output}")

    if output.error:
        print(f"\n[❌] Execution Error: {output.error}")

    if output.data:
        print("\n" + "─" * 80)
        print("📄 Parsed Market Research Analysis Output:")
        print("─" * 80)
        print(json.dumps(output.data, indent=2))
        print("─" * 80)

    print("\n[✓] Test Execution Completed.")


if __name__ == "__main__":
    asyncio.run(run_live_market_research_test())
