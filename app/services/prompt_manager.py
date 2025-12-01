"""Prompt Manager for Demo Agent.

Loads and renders Jinja2 templates with FAQ data for Gemini prompts.
Local implementation to replace external dependency.

Author: Odiseo Team
Created: 2025-11-28
Version: 1.0.0
"""

from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]
from jinja2 import Environment, FileSystemLoader

from app.config.settings import settings
from app.utils.logging import get_logger

logger = get_logger(__name__)


class PromptManager:
    """Manages prompt templates and FAQ data for the Demo Agent.

    Loads Jinja2 templates from prompts/ directory and FAQ data from YAML files.
    Renders complete system prompts for Gemini API calls.

    Attributes:
        prompts_dir: Path to prompts directory.
        env: Jinja2 environment for template loading.
        faq_data: Loaded FAQ data from YAML.
        demo_instructions: Configuration for demo responses.
    """

    def __init__(self) -> None:
        """Initialize PromptManager with templates and data."""
        self.prompts_dir = Path(__file__).parent.parent.parent / "prompts"
        self.env = Environment(
            loader=FileSystemLoader(
                [
                    str(self.prompts_dir),
                    str(self.prompts_dir / "modules"),
                ]
            ),
            autoescape=False,
        )

        # Load FAQ data and configuration
        self.faq_data: list[dict[str, Any]] = []
        self.demo_instructions: dict[str, Any] = {}
        self._load_data()

        logger.info(f"PromptManager initialized with {len(self.faq_data)} FAQ categories")

    def _load_data(self) -> None:
        """Load FAQ data and configuration from YAML files."""
        try:
            # Load demo FAQs
            faq_path = self.prompts_dir / "data" / "demo_faqs.yaml"
            if faq_path.exists():
                with open(faq_path, encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                    self.faq_data = data.get("faqs", [])
                    self.demo_instructions = data.get("demo_instructions", {})
                logger.debug(f"Loaded {len(self.faq_data)} FAQ categories")
            else:
                logger.warning(f"FAQ file not found: {faq_path}")

            # Load prompt versions config
            versions_path = self.prompts_dir / "config" / "prompt_versions.yaml"
            if versions_path.exists():
                with open(versions_path, encoding="utf-8") as f:
                    self.versions_config = yaml.safe_load(f) or {}
            else:
                self.versions_config = {"version": "1.0.0"}

        except Exception as e:
            logger.exception(f"Error loading prompt data: {e}")
            self.faq_data = []
            self.demo_instructions = {}
            self.versions_config = {"version": "1.0.0"}

    def get_demo_prompt(
        self,
        remaining_tokens: int,
        user_lang: str = "es",
    ) -> str:
        """Generate complete system prompt for demo agent.

        Args:
            remaining_tokens: User's remaining token quota.
            user_lang: User language preference (es/en).

        Returns:
            Rendered Jinja2 template as system prompt string.
        """
        try:
            # Get template
            template = self.env.get_template("demo_agent.jinja2")

            # Prepare context
            context = {
                "version": self.versions_config.get("version", "1.0.0"),
                "remaining_tokens": remaining_tokens,
                "user_lang": user_lang,
                "faq_data": self.faq_data,
                "demo_instructions": self.demo_instructions,
                "max_tokens": settings.demo_max_tokens,
                "warning_threshold": settings.demo_warning_threshold,
            }

            # Render template
            prompt = template.render(**context)

            logger.debug(
                f"Generated demo prompt: {len(prompt)} chars, "
                f"lang={user_lang}, tokens_remaining={remaining_tokens}"
            )

            return prompt

        except Exception as e:
            logger.exception(f"Error rendering demo prompt: {e}")
            # Fallback to basic prompt
            return self._get_fallback_prompt(remaining_tokens, user_lang)

    def _get_fallback_prompt(self, remaining_tokens: int, user_lang: str) -> str:
        """Generate fallback prompt if template rendering fails.

        Args:
            remaining_tokens: User's remaining token quota.
            user_lang: User language preference.

        Returns:
            Basic system prompt string.
        """
        if user_lang == "es":
            return f"""Eres un asistente de demostración de Odiseo IA.
Responde preguntas sobre el producto de manera profesional y concisa.
Tokens restantes del usuario: {remaining_tokens}
Si no conoces la respuesta, indica que puedes agendar una llamada con el equipo de ventas."""
        else:
            return f"""You are a demonstration assistant for Odiseo IA.
Answer questions about the product professionally and concisely.
User's remaining tokens: {remaining_tokens}
If you don't know the answer, offer to schedule a call with the sales team."""
