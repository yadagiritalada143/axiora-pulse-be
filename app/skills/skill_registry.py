"""
Skill Registry
──────────────────────────────────────────────────────────────────────────────
Loads all *.md skill files from the skills/ directory at startup.
Each file uses YAML frontmatter (between --- delimiters) for metadata and
a Markdown body for the prompt_template.
Provides a singleton registry that agents use to look up their skill.
"""
import logging
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)

SKILLS_DIR = Path(__file__).parent


# ── Skill object ───────────────────────────────────────────────────────────────

class Skill:
    """Represents a loaded skill from a Markdown skill definition file."""

    def __init__(self, data: dict):
        self.name: str = data.get("name", "")
        self.version: str = str(data.get("version", "1.0"))
        self.purpose: str = data.get("purpose", "")
        self.used_by: str = data.get("used_by", "")
        self.inputs: dict = data.get("inputs", {})
        self.output_schema: dict = data.get("output_schema", {})
        self.guardrails: list[str] = data.get("guardrails", [])
        self.prompt_template: str = data.get("prompt_template", "")

    def get_guardrail_reminder(self) -> str:
        """Format guardrail rules as a block to inject into the prompt."""
        if not self.guardrails:
            return ""
        rules = "\n".join(f"  • {g}" for g in self.guardrails)
        return (
            "══════════════════════════════════════════════════════\n"
            "GUARDRAIL RULES — YOU MUST FOLLOW THESE\n"
            "══════════════════════════════════════════════════════\n"
            f"{rules}"
        )

    def build_prompt(self, **kwargs) -> str:
        """
        Render the prompt template with the given keyword arguments.
        Automatically injects guardrail_reminder.
        """
        kwargs["guardrail_reminder"] = self.get_guardrail_reminder()
        try:
            return self.prompt_template.format(**kwargs)
        except KeyError as e:
            logger.warning(f"[SkillRegistry] Missing prompt variable {e} in skill '{self.name}'")
            # Fill missing variables with a placeholder so the prompt still renders
            import re
            template = self.prompt_template
            missing = re.findall(r"\{(\w+)\}", template)
            for key in missing:
                if key not in kwargs:
                    kwargs[key] = f"[{key}: not provided]"
            kwargs["guardrail_reminder"] = self.get_guardrail_reminder()
            return template.format(**kwargs)

    def __repr__(self) -> str:
        return f"<Skill name={self.name!r} version={self.version!r} used_by={self.used_by!r}>"


# ── Registry singleton ─────────────────────────────────────────────────────────

class SkillRegistry:
    """
    Singleton that loads and caches all skill Markdown files at startup.
    Each *.md file must begin with a YAML frontmatter block (--- ... ---).
    The frontmatter holds metadata; the body becomes the prompt_template.
    Agents call skill_registry.get("skill_name") to retrieve their skill.
    """

    _instance: Optional["SkillRegistry"] = None

    def __new__(cls) -> "SkillRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._skills: dict[str, Skill] = {}
            cls._instance._loaded = False
        return cls._instance

    def load_all(self) -> None:
        """
        Scan the skills/ directory and load every *.md file.
        Each file must start with a YAML frontmatter block (--- ... ---).
        The body after the closing --- becomes the prompt_template.
        Called once at application startup.
        """
        if self._loaded:
            return

        md_files = list(SKILLS_DIR.glob("*.md"))
        if not md_files:
            logger.warning(f"[SkillRegistry] No skill Markdown files found in {SKILLS_DIR}")

        for file in md_files:
            try:
                with open(file, "r", encoding="utf-8") as f:
                    content = f.read()

                # Parse YAML frontmatter delimited by ---
                if not content.startswith("---"):
                    logger.warning(
                        f"[SkillRegistry] Skipping {file.name}: missing frontmatter (no leading ---)"
                    )
                    continue

                parts = content.split("---", 2)
                if len(parts) < 3:
                    logger.warning(
                        f"[SkillRegistry] Skipping {file.name}: malformed frontmatter (no closing ---)"
                    )
                    continue

                data = yaml.safe_load(parts[1]) or {}
                data["prompt_template"] = parts[2].strip()

                if "name" not in data:
                    logger.warning(f"[SkillRegistry] Skipping {file.name}: 'name' missing from frontmatter")
                    continue

                skill = Skill(data)
                self._skills[skill.name] = skill
                logger.info(f"[SkillRegistry] Loaded: {skill.name} v{skill.version}")

            except yaml.YAMLError as e:
                logger.error(f"[SkillRegistry] YAML parse error in {file.name}: {e}")
            except Exception as e:
                logger.error(f"[SkillRegistry] Failed to load {file.name}: {e}")

        self._loaded = True
        logger.info(
            f"[SkillRegistry] Ready — {len(self._skills)} skill(s) loaded: "
            f"{list(self._skills.keys())}"
        )

    def get(self, name: str) -> Optional[Skill]:
        """Return a skill by name. Triggers load if not yet loaded."""
        if not self._loaded:
            self.load_all()

        skill = self._skills.get(name)
        if not skill:
            logger.error(f"[SkillRegistry] Skill not found: '{name}'")
        return skill

    def list_skills(self) -> list[str]:
        """Return names of all loaded skills."""
        if not self._loaded:
            self.load_all()
        return list(self._skills.keys())

    def reload(self) -> None:
        """Force a reload of all skills (useful during development)."""
        self._loaded = False
        self._skills.clear()
        self.load_all()


# Module-level singleton — import this everywhere
skill_registry = SkillRegistry()
