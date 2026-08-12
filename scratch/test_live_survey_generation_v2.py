import asyncio
import json
import logging
import sys
from pathlib import Path

# Add backend directory to path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from app.agents.survey_intelligence_agent import SurveyIntelligenceAgent
from app.guardrails.output_guardrails import OutputValidator
from app.models.agent_models import AgentInput

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_json_repair_and_parser():
    logger.info("=== Testing Truncated JSON Repair & Question Extraction ===")
    validator = OutputValidator()
    
    # 1. Test truncated JSON repair
    truncated_json = '{"survey_title": "AI Pet Collar Survey", "survey_objective": "Test demand", "questions": [{"question_text": "Do you own a dog?", "question_type": "yes_no"}'
    
    repaired, errors = validator.parse_json(truncated_json)
    assert not errors, f"Expected no errors after repair, got: {errors}"
    assert repaired.get("survey_title") == "AI Pet Collar Survey"
    assert len(repaired.get("questions", [])) == 1
    logger.info("✓ Test 1 Passed: Truncated JSON repaired successfully!")
    
    # 2. Test questions extraction from survey_structure sections
    agent = SurveyIntelligenceAgent(None) # gateway not needed for parsing test
    raw_structure_output = json.dumps({
        "survey_title": "Structure Section Survey",
        "survey_objective": "Test section question extraction",
        "survey_structure": {
            "sections": [
                {
                    "section_number": 1,
                    "section_title": "Problem Severity",
                    "questions": [
                        {
                            "question_text": "How severe is the health issue in your pet?",
                            "question_type": "rating_scale",
                            "target_hypothesis": "Quantify pet health pain"
                        }
                    ]
                }
            ]
        },
        "survey_quality_score": 85.0,
        "confidence": 0.9,
        "disclaimer": "Test disclaimer"
    })
    
    parsed = agent._parse_output(raw_structure_output)
    assert len(parsed["questions"]) == 1
    assert parsed["questions"][0]["question_text"] == "How severe is the health issue in your pet?"
    logger.info("✓ Test 2 Passed: Extracted questions from survey_structure sections cleanly!")

if __name__ == "__main__":
    test_json_repair_and_parser()
