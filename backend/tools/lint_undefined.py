"""Static scan for names used but never defined.

compileall only catches syntax errors, so a typo like an undefined module-level
constant would survive until the code path runs in production. This walks the
AST of every module and reports unresolved names.
"""

from __future__ import annotations

import ast
import builtins
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "app"

# Names injected by the runtime or defined implicitly.
GLOBALS = {
    "__name__",
    "__file__",
    "__doc__",
    "__package__",
    "__spec__",
    "self",
    "cls",
    "TYPE_CHECKING",
    "annotations",
}


def module_names(tree: ast.AST) -> set[str]:
    names: set[str] = set(dir(builtins)) | GLOBALS

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                names.add((alias.asname or alias.name).split(".")[0])
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            names.add(node.id)
        elif isinstance(node, ast.arg):
            names.add(node.arg)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            names.add(node.name)
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            names.update(node.names)
        elif isinstance(node, ast.NamedExpr) and isinstance(node.target, ast.Name):
            names.add(node.target.id)

    return names


def main() -> int:
    problems: list[str] = []

    for path in sorted(ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        known = module_names(tree)

        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                if node.id not in known:
                    rel = path.relative_to(ROOT.parent)
                    problems.append(f"{rel}:{node.lineno} undefined name {node.id}")

    unique = sorted(set(problems))
    print(f"scanned {len(list(ROOT.rglob('*.py')))} files")
    print("\n".join(unique) if unique else "no undefined names")
    return 1 if unique else 0


if __name__ == "__main__":
    raise SystemExit(main())