"""CLAUDE.local.md says comments are one line. Three PRs running, they were not."""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SOURCES = sorted((ROOT / "app").rglob("*.py")) + sorted((ROOT / "tests").rglob("*.py"))


def comment_runs(path: Path) -> list[tuple[int, str]]:
    runs, start, length = [], 0, 0
    for number, raw in enumerate(path.read_text().splitlines(), start=1):
        line = raw.strip()
        if line.startswith("#"):
            length += 1
            start = start or number
        else:
            if length > 1:
                runs.append((start, line))
            start, length = 0, 0
    if length > 1:
        runs.append((start, ""))
    return runs


@pytest.mark.parametrize("path", SOURCES, ids=lambda p: p.name)
def test_no_comment_runs_longer_than_one_line(path):
    runs = comment_runs(path)

    assert not runs, (
        f"{path.relative_to(ROOT)} has multi-line comments at lines "
        f"{[line for line, _ in runs]}. One line, then docs/DECISIONS.md."
    )
