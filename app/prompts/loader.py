"""Tiny loader for markdown prompt templates in this directory."""
import re
from pathlib import Path

_PROMPTS_DIR = Path(__file__).parent


def load_prompt(name: str) -> str:
    """Load a prompt template by filename (e.g. 'node_summary_beginner.md')."""
    path = _PROMPTS_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"Prompt template not found: {path}")
    return path.read_text(encoding="utf-8")


def render_prompt(name: str, variables: dict) -> str:
    """Load a template and substitute {{var}} placeholders."""
    template = load_prompt(name)
    # Replace {{ key }} (with optional whitespace) with values from variables.
    def _sub(m: re.Match) -> str:
        key = m.group(1).strip()
        return str(variables.get(key, m.group(0)))
    return re.sub(r"\{\{\s*([\w_]+)\s*\}\}", _sub, template)