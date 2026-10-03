"""Parse every Python file and report syntax errors."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
files = sorted(root.glob("app/**/*.py")) + sorted(root.glob("tools/*.py"))

bad: list[str] = []
for path in files:
    try:
        ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError as exc:
        bad.append(f"{path.relative_to(root)}:{exc.lineno}: {exc.msg}")

report = "\n".join(bad) if bad else "SYNTAX OK"
Path("syntax_report.txt").write_text(
    f"checked {len(files)} files\n\n{report}\n", encoding="utf-8"
)
print(report)
sys.exit(1 if bad else 0)