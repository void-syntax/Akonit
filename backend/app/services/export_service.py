"""Automated cross-source signal export service (JSON & Markdown Briefings)."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models import Signal, Source
from app.models.enums import SignalStatus

logger = get_logger(__name__)


async def export_intelligence_digest(session: AsyncSession, period: str = "daily") -> dict[str, str]:
    """Export daily/weekly intelligence digests as clean Markdown reports and JSON packages into exports/ in project root."""
    project_root = Path(__file__).resolve().parent.parent.parent.parent
    exports_dir = project_root / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)

    date_str = datetime.now(UTC).strftime("%Y-%m-%d")

    # Fetch key signal metrics
    total_signals = (await session.execute(select(func.count(Signal.id)))).scalar() or 0
    breakouts = (await session.execute(
        select(Signal).where(Signal.status == SignalStatus.BREAKOUT).order_by(Signal.strength.desc()).limit(10)
    )).scalars().all()
    
    top_alpha = (await session.execute(
        select(Signal)
        .where(Signal.status != SignalStatus.FADING)
        .order_by(Signal.strength.desc())
        .limit(10)
    )).scalars().all()

    sources_count = (await session.execute(select(func.count(Source.id)))).scalar() or 0

    digest_data = {
        "generated_at": datetime.now(UTC).isoformat(),
        "period": period,
        "summary": {
            "total_signals": total_signals,
            "breakouts_count": len(breakouts),
            "tracked_sources": sources_count,
        },
        "breakouts": [
            {
                "id": s.id,
                "title": s.title,
                "strength": s.strength,
                "growth": s.growth,
                "source_id": s.source_id,
                "url": s.source_url,
                "ai_priority": s.ai_priority,
            }
            for s in breakouts
        ],
        "top_alpha": [
            {
                "id": s.id,
                "title": s.title,
                "strength": s.strength,
                "growth": s.growth,
                "source_id": s.source_id,
                "url": s.source_url,
                "ai_priority": s.ai_priority,
            }
            for s in top_alpha
        ],
    }

    # JSON package path
    json_path = exports_dir / f"signal_radar_digest_{date_str}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(digest_data, f, indent=2, ensure_ascii=False)

    # Markdown report path
    md_path = exports_dir / f"signal_radar_digest_{date_str}.md"
    md_lines = [
        f"# 📡 Akonit Signal Radar — {period.capitalize()} Intelligence Digest",
        f"**Generated:** {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}  ",
        f"**Total Tracked Signals:** {total_signals} | **Active Sources:** {sources_count} | **Breakouts:** {len(breakouts)}\n",
        "---",
        "## 🚨 Critical Breakouts",
    ]
    if breakouts:
        for s in breakouts:
            md_lines.append(f"- **{s.title}** (STR: `{s.strength:.1f}`, Growth: `+{s.growth:.0f}%`, Source: `{s.source_id}`)")
            if s.source_url:
                md_lines.append(f"  - [Source Link]({s.source_url})")
    else:
        md_lines.append("_No active breakouts recorded in this cycle._")

    md_lines.extend([
        "",
        "---",
        "## 🏆 Top Alpha Intelligence Signals",
    ])
    if top_alpha:
        for s in top_alpha:
            md_lines.append(f"- **{s.title}** — Strength: `{s.strength:.1f}` | Status: `{s.status.value}` | Source: `{s.source_id}`")
            if s.source_url:
                md_lines.append(f"  - [Reference]({s.source_url})")
    else:
        md_lines.append("_No signals available._")

    md_lines.extend([
        "",
        "---",
        "_Akonit Signal Radar Intelligence Engine — Automated Cross-Source Briefing_",
    ])

    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))

    logger.info("Exported intelligence digest to %s and %s", json_path, md_path)
    return {
        "json_path": str(json_path),
        "markdown_path": str(md_path),
    }
