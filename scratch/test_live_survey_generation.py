import asyncio
import json
import logging
import sys
from pathlib import Path

# Add backend directory to path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from app.agents.survey_intelligence_agent import SurveyIntelligenceAgent
from app.llm.llm_gateway import LLMGateway
from app.models.agent_models import AgentInput

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def run_live_test():
    gateway = LLMGateway()
    agent = SurveyIntelligenceAgent(gateway)
    
    agent_input = AgentInput(
        idea_title="PetCare AI - Smart Health Monitor for Dogs",
        idea_description="AI-powered wearable collar for dogs that monitors vital health metrics and alerts owners to early disease signs.",
        problem_statement="Pet owners notice illnesses too late, leading to high vet bills and severe health outcomes for dogs.",
        target_customer="Dog owners aged 25-50 who spend on premium pet care",
        founder_validation_goal="Validate willingness to pay $15/month subscription for health tracking collar.",
    )
    
    logger.info("Running SurveyIntelligenceAgent live execution...")
    result = await agent.run(agent_input)
    
    logger.info(f"Agent Status: {result.status}")
    logger.info(f"Execution Error: {result.error}")
    
    output = result.output
    logger.info(f"Survey Quality Score: {result.score}")
    logger.info(f"Survey Title: {output.get('survey_title')}")
    
    questions = output.get("questions", [])
    logger.info(f"Total Questions Generated: {len(questions)}")
    for i, q in enumerate(questions[:3], 1):
        logger.info(f"Q{i}: {q.get('question_text')}")

if __name__ == "__main__":
    asyncio.run(run_live_test())
