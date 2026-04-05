# SPDX-License-Identifier: Apache-2.0
"""
Configuration and LLM provider management for Aura Research.

Supports OpenAI, Anthropic, and Google Gemini via their native APIs.
Configuration via research.yaml or environment variables.
"""

import os
import logging
from pathlib import Path
from typing import Optional, Dict, List

import yaml

logger = logging.getLogger(__name__)

DEFAULT_MODELS = {
    "openai": "gpt-4o",
    "anthropic": "claude-sonnet-4-20250514",
    "gemini": "gemini-2.0-flash",
}

DEFAULT_CONFIG = {
    "llm": {
        "provider": "openai",
        "model": None,
        "temperature": 0.3,
        "max_tokens": 4096,
    },
    "wiki": {
        "format": "standard",
        "auto_backlinks": True,
    },
    "memory": {
        "enabled": True,
        "auto_write": True,
    },
    "watch": {
        "enabled": False,
        "interval": 5,
    },
    "web_search": {
        "enabled": True,
        "max_results": 5,
    },
}


class ResearchConfig:
    """Project configuration loaded from research.yaml or env vars."""

    def __init__(self, project_dir: Path):
        self.project_dir = Path(project_dir)
        self.config_file = self.project_dir / "research.yaml"
        self.state_dir = self.project_dir / ".research"
        self.raw_dir = self.project_dir / "raw"
        self.wiki_dir = self.project_dir / "wiki"
        self.data = _deep_copy(DEFAULT_CONFIG)

        if self.config_file.exists():
            with open(self.config_file, "r") as f:
                user_config = yaml.safe_load(f) or {}
            _merge(self.data, user_config)

        # Env var overrides
        if os.environ.get("RESEARCH_LLM_PROVIDER"):
            self.data["llm"]["provider"] = os.environ["RESEARCH_LLM_PROVIDER"]
        if os.environ.get("RESEARCH_LLM_MODEL"):
            self.data["llm"]["model"] = os.environ["RESEARCH_LLM_MODEL"]

    @property
    def provider(self) -> str:
        return self.data["llm"]["provider"]

    @property
    def model(self) -> str:
        return self.data["llm"]["model"] or DEFAULT_MODELS.get(self.provider, "gpt-4o")

    @property
    def temperature(self) -> float:
        return self.data["llm"]["temperature"]

    @property
    def max_tokens(self) -> int:
        return self.data["llm"]["max_tokens"]

    @property
    def memory_enabled(self) -> bool:
        return self.data["memory"]["enabled"]

    @property
    def auto_memory(self) -> bool:
        return self.data["memory"]["auto_write"]

    @property
    def web_search_enabled(self) -> bool:
        return self.data["web_search"]["enabled"]

    @property
    def obsidian_mode(self) -> bool:
        return self.data["wiki"]["format"] == "obsidian"

    def save_default(self):
        """Save default config to research.yaml."""
        with open(self.config_file, "w") as f:
            yaml.dump(self.data, f, default_flow_style=False, sort_keys=False)


def _deep_copy(d):
    if isinstance(d, dict):
        return {k: _deep_copy(v) for k, v in d.items()}
    if isinstance(d, list):
        return [_deep_copy(i) for i in d]
    return d


def _merge(base: dict, override: dict):
    for k, v in override.items():
        if k in base and isinstance(base[k], dict) and isinstance(v, dict):
            _merge(base[k], v)
        else:
            base[k] = v


class LLMClient:
    """Unified LLM client supporting OpenAI, Anthropic, and Gemini."""

    def __init__(self, config: ResearchConfig):
        self.config = config
        self.provider = config.provider
        self.model = config.model
        self._client = None
        self._init_client()

    def _init_client(self):
        if self.provider == "openai":
            try:
                from openai import OpenAI
                self._client = OpenAI()
            except ImportError:
                raise ImportError(
                    "OpenAI not installed. Run: pip install 'aura-research[openai]'"
                )
        elif self.provider == "anthropic":
            try:
                import anthropic
                self._client = anthropic.Anthropic()
            except ImportError:
                raise ImportError(
                    "Anthropic not installed. Run: pip install 'aura-research[anthropic]'"
                )
        elif self.provider == "gemini":
            try:
                import google.generativeai as genai
                api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
                if api_key:
                    genai.configure(api_key=api_key)
                self._client = genai.GenerativeModel(self.model)
            except ImportError:
                raise ImportError(
                    "Google GenAI not installed. Run: pip install 'aura-research[gemini]'"
                )
        else:
            raise ValueError(f"Unknown LLM provider: {self.provider}")

        logger.info(f"LLM client initialized: {self.provider}/{self.model}")

    def chat(self, messages: List[Dict[str, str]],
             temperature: Optional[float] = None,
             max_tokens: Optional[int] = None) -> str:
        """Send messages to the LLM and return the response text."""
        temp = temperature or self.config.temperature
        tokens = max_tokens or self.config.max_tokens

        if self.provider == "openai":
            resp = self._client.chat.completions.create(
                model=self.model, messages=messages,
                temperature=temp, max_tokens=tokens,
            )
            return resp.choices[0].message.content

        elif self.provider == "anthropic":
            system_msg = ""
            chat_msgs = []
            for m in messages:
                if m["role"] == "system":
                    system_msg = m["content"]
                else:
                    chat_msgs.append(m)
            kwargs = {"model": self.model, "messages": chat_msgs,
                      "temperature": temp, "max_tokens": tokens}
            if system_msg:
                kwargs["system"] = system_msg
            resp = self._client.messages.create(**kwargs)
            return resp.content[0].text

        elif self.provider == "gemini":
            prompt = "\n\n".join(
                f"{m['role']}: {m['content']}" for m in messages
            )
            resp = self._client.generate_content(
                prompt,
                generation_config={"temperature": temp, "max_output_tokens": tokens},
            )
            return resp.text
