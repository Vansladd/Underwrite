#!/usr/bin/env python3
"""CLAUDE.local.md: comments are one line. Runs over the repo, not one package."""

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SKIP = {".venv", "node_modules", "__pycache__", ".git", ".terraform", "migrations", "scratchpad"}
SUFFIXES = ("*.py", "*.tf", "*.sh")


def comment_runs(path: Path) -> list[int]:
    runs, start, length = [], 0, 0
    for number, raw in enumerate(path.read_text().splitlines(), start=1):
        line = raw.strip()
        if line.startswith("#!"):
            continue
        if line.startswith("#"):
            length += 1
            start = start or number
        else:
            if length > 1:
                runs.append(start)
            start, length = 0, 0
    return runs + ([start] if length > 1 else [])


def main() -> int:
    offenders = []
    for suffix in SUFFIXES:
        for path in sorted(REPO.rglob(suffix)):
            if SKIP & set(path.parts):
                continue
            for line in comment_runs(path):
                offenders.append(f"{path.relative_to(REPO)}:{line}")

    for offender in offenders:
        print(f"multi-line comment: {offender}", file=sys.stderr)
    if offenders:
        print("\nOne line, then docs/DECISIONS.md.", file=sys.stderr)
    return 1 if offenders else 0


if __name__ == "__main__":
    sys.exit(main())
