"""Small shared helpers used by sync.py, generate_readme.py and revision.py."""

from __future__ import annotations

import re
import json
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
SOLUTIONS_DIR = REPO_ROOT / "solutions"
DATA_DIR = REPO_ROOT / "data"
STATE_FILE = DATA_DIR / "synced_submissions.json"

FRONTMATTER_DELIM = "---"


def slugify(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def load_state() -> dict:
    """
    Maps LeetCode question frontend id (str) -> last synced submission id (str).
    This is what prevents duplicate commits/files for a problem already solved.
    """
    if not STATE_FILE.exists():
        return {}
    return json.loads(STATE_FILE.read_text(encoding="utf-8"))


def save_state(state: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_frontmatter_markdown(path: Path, metadata: dict, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fm = yaml.safe_dump(metadata, sort_keys=False, default_flow_style=False).strip()
    content = f"{FRONTMATTER_DELIM}\n{fm}\n{FRONTMATTER_DELIM}\n\n{body.strip()}\n"
    path.write_text(content, encoding="utf-8")


def read_frontmatter_markdown(path: Path) -> tuple[dict, str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith(FRONTMATTER_DELIM):
        return {}, text
    parts = text.split(FRONTMATTER_DELIM, 2)
    if len(parts) < 3:
        return {}, text
    _, fm_raw, body = parts
    metadata = yaml.safe_load(fm_raw) or {}
    return metadata, body.strip()


def iter_problem_readmes():
    """Yield (path, metadata, body) for every solved problem README."""
    if not SOLUTIONS_DIR.exists():
        return
    for readme in sorted(SOLUTIONS_DIR.glob("*/*/README.md")):
        metadata, body = read_frontmatter_markdown(readme)
        if metadata:
            yield readme, metadata, body
