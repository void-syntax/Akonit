"""Interactive Telegram bot for Signal Radar.

Commands:
  /start   - Welcome message and status
  /status  - Current system status (signals count, sources)
  /top     - Top 5 strongest signals right now  
  /new     - Latest 5 NEW signals
  /rising  - Latest 5 RISING signals
  /breakout - Any BREAKOUT signals (urgent)
  /radars  - List active radars
  /mute <hours> - Mute notifications for N hours
  /help    - List all commands
"""
from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("bot.telegram")

_muted_until: datetime | None = None


def is_muted() -> bool:
    global _muted_until
    if _muted_until is None:
        return False
    if datetime.now(UTC) > _muted_until:
        _muted_until = None
        return False
    return True


async def start_bot() -> None:
    """Start the Telegram bot if token is configured."""
    token = settings.telegram_bot_token
    if not token:
        logger.info("TELEGRAM_BOT_TOKEN not set — interactive bot disabled")
        return

    try:
        from telegram import Update
        from telegram.ext import Application, CommandHandler, ContextTypes
    except ImportError:
        logger.warning("python-telegram-bot not installed — interactive bot disabled")
        return

    app = Application.builder().token(token).build()

    async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        await update.message.reply_text(
            "🎯 *Signal Radar Bot (@akonit_analitik_bot)*\n\n"
            "Your personal trend intelligence station is running 24/7.\n\n"
            "*Commands:*\n"
            "/top — Top signals right now\n"
            "/new — Latest new signals\n"
            "/rising — Rising signals\n"
            "/breakout — Breakout alerts\n"
            "/digest — Intelligence digest\n"
            "/sources — Tracked sources\n"
            "/search <kw> — Search signals\n"
            "/status — System status\n"
            "/radars — Your radars\n"
            "/mute 2 — Mute for 2 hours\n"
            "/help — This message",
            parse_mode="Markdown",
        )

    async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        await cmd_start(update, ctx)

    async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        from app.db.session import SessionLocal
        from app.models import Signal, Source
        from app.models.enums import SignalStatus
        from sqlalchemy import func, select

        async with SessionLocal() as session:
            total = (await session.execute(select(func.count(Signal.id)))).scalar() or 0
            active = (await session.execute(
                select(func.count(Signal.id)).where(Signal.status != SignalStatus.FADING)
            )).scalar() or 0
            breakouts = (await session.execute(
                select(func.count(Signal.id)).where(Signal.status == SignalStatus.BREAKOUT)
            )).scalar() or 0
            sources_ok = (await session.execute(select(func.count(Source.id)))).scalar() or 0

        mute_text = ""
        global _muted_until
        if _muted_until and datetime.now(UTC) < _muted_until:
            remaining = int((_muted_until - datetime.now(UTC)).total_seconds() / 60)
            mute_text = f"\n🔕 Muted for {remaining} more minutes"

        await update.message.reply_text(
            f"📡 *Signal Radar Status*\n\n"
            f"🟢 Active signals: *{active}*\n"
            f"🚨 Breakouts: *{breakouts}*\n"
            f"📊 Total tracked: *{total}*\n"
            f"🔌 Sources: *{sources_ok}*\n"
            f"⏰ Time: {datetime.now(UTC).strftime('%H:%M UTC')}"
            f"{mute_text}",
            parse_mode="Markdown",
        )

    async def _send_signals(update: Update, signals: list, title: str) -> None:
        if not update.message:
            return
        if not signals:
            await update.message.reply_text(f"_{title}: none found right now._", parse_mode="Markdown")
            return

        lines = [f"*{title}*\n"]
        for s in signals[:5]:
            growth_str = f"+{s.growth:.0f}%" if s.growth > 0 else f"{s.growth:.0f}%"
            flag = s.flag or "🌐"
            lines.append(
                f"{flag} *{s.title[:60]}*\n"
                f"   📈 {growth_str} · STR {s.strength:.0f} · {s.source_id}\n"
                f"   🔗 {settings.frontend_url}/signals/{s.id}\n"
            )

        await update.message.reply_text("\n".join(lines), parse_mode="Markdown", disable_web_page_preview=True)

    async def cmd_top(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        from app.db.session import SessionLocal
        from app.models import Signal
        from app.models.enums import SignalStatus
        from sqlalchemy import select

        async with SessionLocal() as session:
            signals = (await session.execute(
                select(Signal)
                .where(Signal.status != SignalStatus.FADING)
                .order_by(Signal.strength.desc())
                .limit(5)
            )).scalars().all()
        await _send_signals(update, signals, "🏆 Top Signals")

    async def cmd_new(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        from app.db.session import SessionLocal
        from app.models import Signal
        from app.models.enums import SignalStatus
        from sqlalchemy import select

        async with SessionLocal() as session:
            signals = (await session.execute(
                select(Signal)
                .where(Signal.status == SignalStatus.NEW)
                .order_by(Signal.first_seen_at.desc())
                .limit(5)
            )).scalars().all()
        await _send_signals(update, signals, "🆕 New Signals")

    async def cmd_rising(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        from app.db.session import SessionLocal
        from app.models import Signal
        from app.models.enums import SignalStatus
        from sqlalchemy import select

        async with SessionLocal() as session:
            signals = (await session.execute(
                select(Signal)
                .where(Signal.status == SignalStatus.RISING)
                .order_by(Signal.growth.desc())
                .limit(5)
            )).scalars().all()
        await _send_signals(update, signals, "📈 Rising Signals")

    async def cmd_breakout(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        from app.db.session import SessionLocal
        from app.models import Signal
        from app.models.enums import SignalStatus
        from sqlalchemy import select

        async with SessionLocal() as session:
            signals = (await session.execute(
                select(Signal)
                .where(Signal.status == SignalStatus.BREAKOUT)
                .order_by(Signal.strength.desc())
                .limit(5)
            )).scalars().all()

        if not signals:
            await update.message.reply_text("✅ No breakouts right now. All clear.")
            return
        await _send_signals(update, signals, "🚨 BREAKOUT Signals")

    async def cmd_radars(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        from app.db.session import SessionLocal
        from app.models import Radar
        from sqlalchemy import select

        async with SessionLocal() as session:
            radars = (await session.execute(
                select(Radar).where(Radar.is_active.is_(True)).limit(10)
            )).scalars().all()

        if not radars:
            await update.message.reply_text("_No active radars configured._", parse_mode="Markdown")
            return

        lines = ["*🎯 Active Radars*\n"]
        for r in radars:
            emoji = r.emoji or "🎯"
            lines.append(f"{emoji} *{r.name}* — {r.active_signal_count} signals")

        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

    async def cmd_mute(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        global _muted_until
        hours = 1
        if ctx.args:
            try:
                hours = max(0.5, min(float(ctx.args[0]), 24))
            except ValueError:
                pass
        _muted_until = datetime.now(UTC) + timedelta(hours=hours)
        await update.message.reply_text(
            f"🔕 Notifications muted for {hours:.0f}h. Use /mute 0 to unmute.",
            parse_mode="Markdown",
        )

    async def cmd_digest(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        from app.db.session import SessionLocal
        from app.models import Signal
        from app.models.enums import SignalStatus
        from sqlalchemy import select, func

        async with SessionLocal() as session:
            top_signals = (await session.execute(
                select(Signal)
                .where(Signal.status != SignalStatus.FADING)
                .order_by(Signal.strength.desc())
                .limit(3)
            )).scalars().all()
            breakouts = (await session.execute(
                select(Signal)
                .where(Signal.status == SignalStatus.BREAKOUT)
                .limit(3)
            )).scalars().all()
            total_count = (await session.execute(select(func.count(Signal.id)))).scalar() or 0

        lines = [
            "📊 *Signal Intelligence Daily Digest*",
            f"🕒 Generated at {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}",
            f"📈 Total Tracked Signals: *{total_count}*\n",
        ]

        if breakouts:
            lines.append("🚨 *Top Breakouts:*")
            for s in breakouts:
                lines.append(f"• *{s.title[:50]}* (STR {s.strength:.0f})")
            lines.append("")

        if top_signals:
            lines.append("🏆 *Top Signals:*")
            for s in top_signals:
                lines.append(f"• *{s.title[:50]}* (STR {s.strength:.0f})")

        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

    async def cmd_sources(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        from app.pipeline.collectors import registry_snapshot
        snapshot = registry_snapshot()
        lines = ["🔌 *Tracked Intelligence Sources*\n"]
        for src in snapshot[:12]:
            lines.append(f"• *{src['name']}* (`{src['id']}`) — {src['type']}")
        if len(snapshot) > 12:
            lines.append(f"\n_...and {len(snapshot) - 12} more sources active_")
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

    async def cmd_search(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        if not ctx.args:
            await update.message.reply_text("Usage: `/search <keyword>`", parse_mode="Markdown")
            return
        query = " ".join(ctx.args).strip()
        from app.db.session import SessionLocal
        from app.models import Signal
        from sqlalchemy import select, or_

        async with SessionLocal() as session:
            signals = (await session.execute(
                select(Signal)
                .where(or_(Signal.title.ilike(f"%{query}%"), Signal.description.ilike(f"%{query}%")))
                .order_by(Signal.strength.desc())
                .limit(5)
            )).scalars().all()

        await _send_signals(update, signals, f"🔍 Search results for '{query}'")

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("top", cmd_top))
    app.add_handler(CommandHandler("new", cmd_new))
    app.add_handler(CommandHandler("rising", cmd_rising))
    app.add_handler(CommandHandler("breakout", cmd_breakout))
    app.add_handler(CommandHandler("radars", cmd_radars))
    app.add_handler(CommandHandler("mute", cmd_mute))
    app.add_handler(CommandHandler("digest", cmd_digest))
    app.add_handler(CommandHandler("sources", cmd_sources))
    app.add_handler(CommandHandler("search", cmd_search))

    logger.info("Telegram bot starting in polling mode (@akonit_analitik_bot)")
    await app.initialize()
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True)
    logger.info("Telegram bot is running successfully")
