---
name: market_research_skill
version: "1.0"
purpose: >
  Generate market understanding and opportunity sizing from founder context.
used_by: market_research_agent

inputs:
  required:
    - idea_title
    - idea_description
  optional:
    - industry
    - geography

output_schema:
  market_opportunity_score:
    type: integer
    range: [0, 100]
  market_opportunity_summary:
    type: string
  target_customer_segments:
    type: array
  competitor_overview:
    type: array
  opportunity_signals:
    type: array
  risk_signals:
    type: array
  confidence:
    type: float
    range: [0.0, 1.0]

guardrails:
  - Mention when market data is directional or general.
  - Do not claim real-time market data unless connected to external search tools.
  - Do not fabricate statistics or market size numbers.
---
Perform market research for: {idea_title}.
Return JSON containing market_opportunity_score, market_opportunity_summary, target_customer_segments, competitor_overview, opportunity_signals, risk_signals, confidence.
Ensure you follow these guardrails:
{guardrail_reminder}
