"""
Output Guardrails Module
──────────────────────────────────────────────────────────────────────────────
Enforces strict verification on all agent output payloads before returning to callers.

Validation standard:
  1. JSON validity check & JSON block extraction.
  2. Required fields presence check.
  3. Score and confidence range clamping (e.g. 0–100 score, 0.0–1.0 confidence).
  4. Decision-support disclaimer injection.
  5. Forbidden advice detection (e.g. financial guarantees, legal advice, illegal claims).
"""
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_DISCLAIMER = (
    "This output provides decision-support guidance only. "
    "It does not constitute formal legal, financial, or tax advice."
)

DEFAULT_FORBIDDEN_PATTERNS = [
    r"guarantees?\s+(\$\d+|\d+%\s+returns?|revenue|profit)",
    r"100%\s+guaranteed",
    r"cannot\s+fail",
    r"risk-free\s+investment",
    r"consult\s+me\s+instead\s+of\s+a\s+lawyer",
    r"legal\s+contract\s+is\s+binding\s+without\s+review",
]


@dataclass
class ValidationResult:
    is_valid: bool
    data: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    forbidden_advice_flagged: bool = False


class OutputValidator:
    """
    Comprehensive Output Validation Engine for Axiora Pulse Agents.
    """

    def __init__(
        self,
        default_disclaimer: str = DEFAULT_DISCLAIMER,
        forbidden_patterns: list[str] | None = None,
    ) -> None:
        self.default_disclaimer = default_disclaimer
        self.forbidden_patterns = forbidden_patterns or DEFAULT_FORBIDDEN_PATTERNS

    def _attempt_json_repair(self, text: str) -> dict[str, Any] | None:
        """Attempt to repair truncated JSON text by balancing quotes and closing brackets/braces."""
        if not text or "{" not in text:
            return None

        start_idx = text.find("{")
        snippet = text[start_idx:].strip()

        open_brackets = 0
        open_braces = 0
        in_string = False
        escape = False

        for char in snippet:
            if escape:
                escape = False
                continue
            if char == "\\" and in_string:
                escape = True
                continue
            if char == '"':
                in_string = not in_string
                continue
            if not in_string:
                if char == "[":
                    open_brackets += 1
                elif char == "]":
                    open_brackets = max(0, open_brackets - 1)
                elif char == "{":
                    open_braces += 1
                elif char == "}":
                    open_braces = max(0, open_braces - 1)

        repaired = snippet
        if in_string:
            repaired += '"'
        repaired += "]" * open_brackets
        repaired += "}" * open_braces

        try:
            parsed = json.loads(repaired)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass
        return None

    def parse_json(self, raw_content: str) -> tuple[dict[str, Any], list[str]]:
        """Extract and parse valid JSON object from raw LLM output text."""
        errors: list[str] = []
        if not raw_content or not raw_content.strip():
            return {}, ["Empty output content."]

        # Attempt direct JSON parse
        try:
            parsed = json.loads(raw_content)
            if isinstance(parsed, dict):
                return parsed, []
        except json.JSONDecodeError:
            pass

        # Attempt regex extraction of JSON object block
        match = re.search(r"\{.*\}", raw_content, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group())
                if isinstance(parsed, dict):
                    return parsed, []
            except json.JSONDecodeError:
                pass

        # Attempt repair of truncated JSON block
        repaired_dict = self._attempt_json_repair(raw_content)
        if repaired_dict is not None:
            logger.info("Successfully repaired truncated JSON output from LLM.")
            return repaired_dict, []

        errors.append("Failed to parse valid JSON from LLM output.")
        return {}, errors

    def check_required_fields(
        self, data: dict[str, Any], required_fields: list[str]
    ) -> tuple[bool, list[str]]:
        """Verify presence of all mandatory schema fields."""
        missing = [f for f in required_fields if f not in data or data[f] is None]
        if missing:
            return False, [f"Missing required field(s): {', '.join(missing)}"]
        return True, []

    def clamp_numeric_ranges(
        self, data: dict[str, Any], range_specs: dict[str, tuple[float, float]]
    ) -> tuple[dict[str, Any], list[str]]:
        """
        Clamp numeric fields to specified range boundaries [min_val, max_val].
        e.g., {'score': (0.0, 100.0), 'confidence': (0.0, 1.0)}
        """
        warnings: list[str] = []
        clamped = dict(data)

        for field_name, (min_val, max_val) in range_specs.items():
            if field_name in clamped and clamped[field_name] is not None:
                try:
                    val = float(clamped[field_name])
                    if val < min_val:
                        warnings.append(
                            f"Field '{field_name}' ({val}) below minimum {min_val}. Clamped to {min_val}."
                        )
                        val = min_val
                    elif val > max_val:
                        warnings.append(
                            f"Field '{field_name}' ({val}) above maximum {max_val}. Clamped to {max_val}."
                        )
                        val = max_val
                    clamped[field_name] = val
                except (ValueError, TypeError):
                    warnings.append(f"Field '{field_name}' is not numeric. Setting default fallback.")
                    clamped[field_name] = min_val

        return clamped, warnings

    def ensure_disclaimer(self, data: dict[str, Any]) -> dict[str, Any]:
        """Inject standard decision-support disclaimer if missing or blank."""
        data_copy = dict(data)
        existing = data_copy.get("disclaimer")
        if not existing or not str(existing).strip():
            data_copy["disclaimer"] = self.default_disclaimer
        return data_copy

    def scan_forbidden_advice(self, data: dict[str, Any]) -> tuple[bool, list[str]]:
        """
        Scan full text representation of output dictionary for forbidden advice patterns.
        """
        warnings: list[str] = []
        text_repr = json.dumps(data, ensure_ascii=False)
        flagged = False

        for pattern in self.forbidden_patterns:
            if re.search(pattern, text_repr, re.IGNORECASE):
                flagged = True
                warnings.append(f"Forbidden advice pattern detected: '{pattern}'.")

        return flagged, warnings

    def validate_all(
        self,
        raw_content: str,
        required_fields: list[str],
        range_specs: dict[str, tuple[float, float]] | None = None,
        default_values: dict[str, Any] | None = None,
    ) -> ValidationResult:
        """
        Full 5-point output validation pipeline execution:
        1. JSON syntax
        2. Required fields check (with default injection if provided)
        3. Score & range bounds check
        4. Disclaimer enforcement
        5. Forbidden advice detection
        """
        errors: list[str] = []
        warnings: list[str] = []

        # 1. Parse JSON
        parsed_data, json_errors = self.parse_json(raw_content)
        if json_errors:
            return ValidationResult(is_valid=False, errors=json_errors)

        # Apply defaults for missing fields if default_values provided
        if default_values:
            for k, v in default_values.items():
                parsed_data.setdefault(k, v)

        # 2. Required fields check
        is_complete, field_errors = self.check_required_fields(parsed_data, required_fields)
        if not is_complete:
            errors.extend(field_errors)

        # 3. Range specs clamping
        if range_specs:
            parsed_data, range_warnings = self.clamp_numeric_ranges(parsed_data, range_specs)
            warnings.extend(range_warnings)

        # 4. Disclaimer enforcement
        parsed_data = self.ensure_disclaimer(parsed_data)

        # 5. Forbidden advice scan
        flagged, forbidden_warnings = self.scan_forbidden_advice(parsed_data)
        warnings.extend(forbidden_warnings)
        if flagged:
            warnings.append("Output contains potentially unverified or forbidden advice strings.")

        is_valid = len(errors) == 0

        return ValidationResult(
            is_valid=is_valid,
            data=parsed_data,
            errors=errors,
            warnings=warnings,
            forbidden_advice_flagged=flagged,
        )


# Global default validator singleton instance
output_validator = OutputValidator()
