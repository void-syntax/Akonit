"""Print a readable tail of an e2e run log (handles UTF-8 + BOM)."""

from __future__ import annotations

import sys
from pathlib import Path

path = Path(sys.argv[1] if len(sys.argv) > 1 else "final_e2e.txt")
count = int(sys.argv[2]) if len(sys.argv) > 2 else 60

text = path.read_text(encoding="utf-8", errors="replace").replace("\r", "")
lines = [line[:170] for line in text.splitlines() if line.strip()]
Path("tail.txt").write_text(
    f"{path.name}: {len(lines)} lines\n\n" + "\n".join(lines[-count:]),
    encoding="utf-8",
)