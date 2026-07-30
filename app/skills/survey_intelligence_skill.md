---
name: survey_intelligence_skill
version: "1.0"
purpose: >
  Design unbiased, targeted customer validation surveys and analyze key assumptions to generate actionable feedback questions.
used_by: survey_intelligence_agent

inputs:
  required:
    - idea_title
    - idea_description
  optional:
    - problem_statement
    - target_customer
    - validation_goal

output_schema:
  survey_title:
    type: string
  survey_objective:
    type: string
  target_audience_summary:
    type: string
  questions:
    type: array
    items:
      question_text: string
      question_type: string # multiple_choice | open_ended | rating_scale
      target_hypothesis: string
  survey_quality_score:
    type: float
    range: [0.0, 100.0]
  confidence:
    type: float
    range: [0.0, 1.0]
  disclaimer:
    type: string

guardrails:
  - Keep surveys short, sweet, and engaging (5 to 8 questions max).
  - Avoid biased, leading, or hypothetical questions (ask about past behavior, not future promises).
  - Do not ask for sensitive personal data or financial credentials.
  - Do not guarantee product success or financial returns.
---
Generate a customer validation survey for the following startup concept:

Startup Idea Title: {idea_title}
Description: {idea_description}
Problem Statement: {problem_statement}
Target Customer Profile: {target_customer}
Validation Goal: {validation_goal}

Respond ONLY with a valid JSON object matching this schema:
{{
  "survey_title": "Descriptive, engaging survey title for prospective respondents",
  "survey_objective": "Clear hypothesis statement this survey tests",
  "target_audience_summary": "Summary of ideal survey respondent cohort",
  "questions": [
    {{
      "question_text": "Exact text of the question",
      "question_type": "multiple_choice | open_ended | rating_scale",
      "target_hypothesis": "The specific assumption or pain point being tested"
    }}
  ],
  "survey_quality_score": 85.0,
  "confidence": 0.85,
  "disclaimer": "This output provides decision-support guidance only. It does not constitute formal legal, financial, or tax advice."
}}

{guardrail_reminder}
