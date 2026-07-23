---
name: gtm_strategy_skill
version: "1.0"
purpose: >
  Suggest early customer acquisition, traction strategy, and positioning.
used_by: gtm_strategy_agent

inputs:
  required:
    - idea_title
    - idea_description
  optional:
    - target_customer

output_schema:
  gtm_readiness_score:
    type: integer
    range: [0, 100]
  positioning_recommendation:
    type: string
  acquisition_channels:
    type: array
  early_traction_ideas:
    type: array
  messaging_suggestions:
    type: array
  confidence:
    type: float
    range: [0.0, 1.0]

guardrails:
  - Focus on early validation and organic traction.
  - Avoid expensive, large-scale marketing suggestions for MVP stage.
  - Keep recommendations highly practical and low-cost.
---
Analyze the Go-To-Market strategy for: {idea_title}.
Return JSON containing gtm_readiness_score, positioning_recommendation, acquisition_channels, early_traction_ideas, messaging_suggestions, confidence.
Ensure you follow these guardrails:
{guardrail_reminder}
