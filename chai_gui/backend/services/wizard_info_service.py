"""
OpenCHAI GUI — Wizard Section Info Service

Serves the per-section Markdown help content shown in the CHAI Release
wizard's info sidebar. Content lives in backend/docs/wizard_sections/*.md
as plain files so non-developers can edit the wording without touching
any Python or JS.

This is intentionally a brand-new, self-contained module — it does not
modify any existing route or service file.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List

_DOCS_DIR = Path(__file__).resolve().parent.parent / "docs" / "wizard_sections"

# Maps the wizard's internal step key -> markdown filename.
# Keys correspond to the STEPS ids used by ChaiReleaseWizard.jsx:
#   0 auth | 1 arch_os | 2 release | 3 version | 4 execute | 5 containers
_SECTION_FILES: Dict[str, str] = {
    "auth":       "auth.md",
    "arch_os":    "arch_os.md",
    "release":    "release.md",
    "version":    "version.md",
    "execute":    "execute.md",
    "containers": "containers.md",
}


def list_sections() -> List[str]:
    return list(_SECTION_FILES.keys())


def get_section_info(section: str) -> Dict[str, str]:
    """
    Returns {"section": str, "content": str} for the given section key.
    Returns an empty content string (not an error) if the file is missing,
    so a missing doc never breaks the wizard — the info panel just shows
    nothing instead of crashing the page.
    """
    filename = _SECTION_FILES.get(section)
    if not filename:
        return {"section": section, "content": ""}

    path = _DOCS_DIR / filename
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        content = ""

    return {"section": section, "content": content}


def get_all_sections() -> Dict[str, str]:
    """Returns {section_key: markdown_content} for every known section —
    lets the frontend fetch everything in a single request on mount."""
    return {key: get_section_info(key)["content"] for key in _SECTION_FILES}
