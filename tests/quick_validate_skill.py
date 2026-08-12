"""CI copy of the Codex Skill metadata publication check."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml


ALLOWED_PROPERTIES = {"name", "description", "license", "allowed-tools", "metadata"}


def validate_skill(skill_path: Path) -> tuple[bool, str]:
    skill_md = skill_path / "SKILL.md"
    if not skill_md.is_file():
        return False, "SKILL.md not found"
    content = skill_md.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
    if not match:
        return False, "Invalid or missing YAML frontmatter"
    try:
        frontmatter = yaml.safe_load(match.group(1))
    except yaml.YAMLError as exc:
        return False, f"Invalid YAML in frontmatter: {exc}"
    if not isinstance(frontmatter, dict):
        return False, "Frontmatter must be a YAML dictionary"
    unexpected = set(frontmatter) - ALLOWED_PROPERTIES
    if unexpected:
        return False, f"Unexpected frontmatter keys: {sorted(unexpected)}"
    if set(frontmatter) != {"name", "description"}:
        return False, "This Skill requires exactly name and description frontmatter"
    name = frontmatter["name"]
    description = frontmatter["description"]
    if not isinstance(name, str) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name):
        return False, "Skill name must be nonempty hyphen-case"
    if len(name) > 64:
        return False, "Skill name exceeds 64 characters"
    if not isinstance(description, str) or not description.strip():
        return False, "Skill description must be nonempty text"
    if len(description) > 1024 or "<" in description or ">" in description:
        return False, "Skill description violates the publication contract"
    return True, "Skill is valid!"


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: quick_validate_skill.py <skill-directory>")
    valid, message = validate_skill(Path(sys.argv[1]))
    print(message)
    raise SystemExit(0 if valid else 1)
