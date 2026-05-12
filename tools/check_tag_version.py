#!/usr/bin/env python3
"""
check_tag_version.py

Checks that the provided tag (e.g., 1.2.3) matches the version in pyproject.toml.
Usage: python check_tag_version.py <tag>
- Exits 0 if match, 1 if not.
- Prints error to stderr if mismatch.
"""
import sys
import re
from pathlib import Path

def get_pyproject_version(pyproject_path: Path) -> str:
    text = pyproject_path.read_text(encoding="utf-8")
    m = re.search(r"^version\s*=\s*['\"]([^'\"]+)['\"]", text, re.MULTILINE)
    if not m:
        print("[ERROR] Could not find version in pyproject.toml", file=sys.stderr)
        sys.exit(2)
    return m.group(1)

def main():
    if len(sys.argv) != 2:
        print("Usage: python check_tag_version.py <tag>", file=sys.stderr)
        sys.exit(2)
    tag = sys.argv[1].lstrip("vV")
    pyproject = Path(__file__).parent.parent / "pyproject.toml"
    version = get_pyproject_version(pyproject)
    if tag == version:
        print(f"[OK] Tag {tag} matches version {version} in pyproject.toml.")
        sys.exit(0)
    else:
        print(f"[ERROR] Tag {tag} does NOT match version {version} in pyproject.toml!", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
