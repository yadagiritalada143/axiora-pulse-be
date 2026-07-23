---
name: financial_readiness_skill
version: "1.0"
purpose: >
  Provide basic financial-readiness guidance based on founder-provided inputs.
used_by: financial_readiness_agent

inputs:
  required:
    - idea_title
    - idea_description
  optional:
    - budget_range
    - revenue_model_assumption
    - pricing_assumption

output_schema:
  financial_readiness_score:
    type: integer
    range: [0, 100]
  cost_category_summary:
    type: array
  revenue_model_options:
    type: array
  pricing_consideration_notes:
    type: array
  funding_gap_awareness:
    type: string
  financial_risk_flags:
    type: array
  confidence:
    type: float
    range: [0.0, 1.0]

guardrails:
  - This skill must not provide loan eligibility advice, tax advice, investment advice, accounting advice, valuation advice, banking advice, or professional financial planning.
  - Must include educational disclaimer: "This is educational and decision-support guidance only. It is not legal, tax, accounting, banking, investment, loan, or professional financial advice."
---
Analyze the financial readiness for the venture: {idea_title}.
Return JSON containing financial_readiness_score, cost_category_summary, revenue_model_options, pricing_consideration_notes, funding_gap_awareness, financial_risk_flags, confidence.
Ensure you follow these guardrails:
{guardrail_reminder}
