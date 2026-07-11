"""Phase 4 — Scan app/prompts/library/*.md for seeded system templates.

Each file name is `<category>_<name>.md`. The category is the part before
the first underscore (`knowledge_exploration_concept_deepdive.md` →
`Knowledge Exploration` / `concept_deepdive`). The display name is the
human-friendly title of the file.

We keep this here (not in app/prompts/loader.py) so prompts/loader stays
agnostic of the library seed rule.
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Dict

_LIBRARY_DIR = Path(__file__).resolve().parents[1] / "prompts" / "library"


def get_system_prompts() -> List[Dict[str, str]]:
    """Return the seeded templates as [{name, category, template}, ...]."""
    out: List[Dict[str, str]] = []
    if not _LIBRARY_DIR.exists():
        return out
    for path in sorted(_LIBRARY_DIR.glob("*.md")):
        if path.name.startswith("_"):  # ignore hidden/notes
            continue
        stem = path.stem  # e.g. "knowledge_exploration_concept_deepdive"
        parts = stem.split("_", 1)
        category = _humanize(parts[0]) if parts else "General"
        slug = parts[1] if len(parts) > 1 else stem
        out.append({
            "name": _humanize(slug),
            "category": category,
            "template": path.read_text(encoding="utf-8").strip(),
        })
    return out


def _humanize(slug: str) -> str:
    return slug.replace("_", " ").strip().title()
