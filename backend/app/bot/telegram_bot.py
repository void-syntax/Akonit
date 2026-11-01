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
import hashlib
from datetime import UTC, datetime, timedelta

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("bot.telegram")

_muted_until: datetime | None = None
_configuration_changed = asyncio.Event()
_recent_private_chats: dict[str, tuple[datetime, str, str | None]] = {}


def notify_bot_config_changed() -> None:
    """Wake the bot manager after a token is added, replaced, or removed."""
    _configuration_changed.set()


def _select_token(encrypted_tokens: list[str | None], fallback: str | None) -> str | None:
    """Select the configured local bot token without logging credential data."""
    from app.core.secrets import decrypt_secret

    for encrypted in encrypted_tokens:
        if encrypted:
            try:
                return decrypt_secret(encrypted)
            except RuntimeError:
                logger.exception("Could not decrypt a saved Telegram bot token")
    return fallback


async def _configured_token() -> str | None:
    """Read the saved profile token, falling back to the environment setting."""
    from sqlalchemy import select
    from app.db.session import SessionLocal
    from app.models.user import UserProfile

    async with SessionLocal() as session:
        encrypted = (await session.execute(
            select(UserProfile.telegram_bot_token_encrypted).where(
                UserProfile.telegram_bot_token_encrypted.isnot(None)
            ).order_by(UserProfile.created_at.asc())
        )).scalars().all()
    return _select_token(encrypted, settings.telegram_bot_token)


def remember_private_chat(token: str, chat_id: int, name: str | None) -> None:
    """Remember a recent /start for the Settings flow; never link it silently."""
    token_key = hashlib.sha256(token.encode("utf-8")).hexdigest()
    _recent_private_chats[token_key] = (datetime.now(UTC), str(chat_id), name)


def find_recent_private_chat(token: str) -> tuple[str, str | None] | None:
    """Return a recent /start chat without competing with the active poller."""
    token_key = hashlib.sha256(token.encode("utf-8")).hexdigest()
    recent = _recent_private_chats.get(token_key)
    if recent is None:
        return None
    seen_at, chat_id, name = recent
    if datetime.now(UTC) - seen_at > timedelta(minutes=10):
        _recent_private_chats.pop(token_key, None)
        return None
    return chat_id, name


def format_telegram_bulletin(signal, radar_name: str | None = None) -> str:
    flag = signal.flag or "🚨"
    growth_str = f"+{signal.growth:.0f}%" if signal.growth > 0 else f"{signal.growth:.0f}%"
    radar_info = f"🎯 Radar: *{radar_name}*\n" if radar_name else ""
    return (
        f"🚨 *AKONIT INTELLIGENCE BULLETIN* 🚨\n\n"
        f"{flag} *{signal.title}*\n\n"
        f"📊 Strength: *{signal.strength:.1f}* · Growth: *{growth_str}*\n"
        f"🔌 Source: `{signal.source_id}` · Status: *{signal.status.value.upper()}*\n"
        f"{radar_info}"
        f"🔗 [View Signal Details]({settings.frontend_url}/signals/{signal.id})"
    )


async def _background_alert_dispatcher(token: str) -> None:
    """Background loop monitoring for critical/breakout signals with high alpha score and pushing bulletins to configured user chat IDs."""
    notified_signal_ids: set[str] = set()
    await asyncio.sleep(10)

    while True:
        try:
            if is_muted():
                await asyncio.sleep(60)
                continue

            from app.db.session import SessionLocal
            from app.models import Signal
            from app.models.enums import SignalStatus
            from app.models.user import UserProfile
            from app.notifications.telegram import TelegramClient
            from sqlalchemy import select, or_

            async with SessionLocal() as session:
                profiles = (await session.execute(
                    select(UserProfile).where(
                        UserProfile.telegram_chat_id.isnot(None),
                        UserProfile.telegram_alerts_enabled.is_(True)
                    )
                )).scalars().all()

                signals = (await session.execute(
                    select(Signal)
                    .where(
                        or_(
                            Signal.status == SignalStatus.BREAKOUT,
                            Signal.ai_priority == "critical",
                        )
                    )
                    .order_by(Signal.strength.desc())
                    .limit(5)
                )).scalars().all()

                if not profiles:
                    logger.debug("Telegram background dispatcher: no user profiles with telegram_alerts_enabled and telegram_chat_id configured. Skipping broadcast.")
                    for s in signals:
                        notified_signal_ids.add(s.id)
                else:
                    async with TelegramClient(token=token) as client:
                        for s in signals:
                            if s.id in notified_signal_ids:
                                continue
                            if s.strength >= 60 or s.ai_priority == "critical":
                                bulletin = format_telegram_bulletin(s)
                                for profile in profiles:
                                    chat_id = profile.telegram_chat_id
                                    if not chat_id or chat_id.strip() in ("", "@akonit_analitik_bot"):
                                        continue
                                    try:
                                        await client.send(chat_id, bulletin)
                                        logger.info("Pushed automated background intelligence bulletin for signal %s to chat_id %s", s.id, chat_id)
                                    except Exception as ex:
                                        logger.warning("Failed to push automated telegram bulletin for %s to %s: %r", s.id, chat_id, ex)
                                    await asyncio.sleep(1)
                                notified_signal_ids.add(s.id)
        except Exception as exc:
            logger.warning("Error in background telegram alert dispatcher: %r", exc)

        await asyncio.sleep(300)


def is_muted() -> bool:
    global _muted_until
    if _muted_until is None:
        return False
    if datetime.now(UTC) > _muted_until:
        _muted_until = None
        return False
    return True


async def _run_bot(token: str) -> None:
    """Run the polling application for one configured token."""
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
        chat = update.effective_chat
        if chat and chat.type == "private":
            remember_private_chat(token, chat.id, chat.first_name or chat.username)
        link_message = (
            "\n\nOpen Settings and choose Find my chat to link alerts."
            if chat and chat.type == "private"
            else "\n\nOpen the bot in a private chat and press Start to link alerts."
        )
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
            "/help — This message" + link_message,
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

        lines = [title, ""]
        for s in signals[:5]:
            growth_str = f"+{s.growth:.0f}%" if s.growth > 0 else f"{s.growth:.0f}%"
            flag = s.flag or "🌐"
            lines.append(
                f"{flag} {s.title[:60]}\n"
                f"   📈 {growth_str} · STR {s.strength:.0f} · {s.source_id}\n"
                f"   🔗 {settings.frontend_url}/signals/{s.id}\n"
            )

        # Titles and source IDs originate from public feeds. Plain text avoids
        # malformed Markdown breaking the entire Telegram reply.
        await update.message.reply_text("\n".join(lines), disable_web_page_preview=True)

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

    async def cmd_summary(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        from app.db.session import SessionLocal
        from app.models import Signal
        from sqlalchemy import select

        async with SessionLocal() as session:
            signals = (await session.execute(
                select(Signal)
                .order_by(Signal.strength.desc())
                .limit(5)
            )).scalars().all()
        await _send_signals(update, signals, "⚡ Top 5 Alpha Signals (Summary)")

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
    app.add_handler(CommandHandler("summary", cmd_summary))
    app.add_handler(CommandHandler("search", cmd_search))

    dispatcher_task: asyncio.Task | None = None
    initialized = False
    started = False
    polling = False
    try:
        await app.initialize()
        initialized = True
        await app.start()
        started = True
        await app.updater.start_polling(drop_pending_updates=False)
        polling = True
        dispatcher_task = asyncio.create_task(
            _background_alert_dispatcher(token), name="telegram-alert-dispatcher"
        )
        logger.info("Telegram bot is running successfully")
        await asyncio.Event().wait()
    finally:
        if dispatcher_task is not None:
            dispatcher_task.cancel()
            try:
                await dispatcher_task
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.exception("Telegram alert dispatcher failed during shutdown")
        if polling and app.updater is not None:
            await app.updater.stop()
        if started:
            await app.stop()
        if initialized:
            await app.shutdown()


async def start_bot() -> None:
    """Keep the bot available and apply profile token changes without API restart."""
    while True:
        _configuration_changed.clear()
        try:
            token = await _configured_token()
            if not token:
                logger.info("Telegram bot waiting for a token in Profile settings")
                try:
                    await asyncio.wait_for(_configuration_changed.wait(), timeout=30.0)
                except TimeoutError:
                    pass
            else:
                running = asyncio.create_task(_run_bot(token), name="telegram-polling")
                changed = asyncio.create_task(_configuration_changed.wait())
                done, pending = await asyncio.wait(
                    {running, changed}, return_when=asyncio.FIRST_COMPLETED
                )
                if changed in done:
                    running.cancel()
                    try:
                        await running
                    except asyncio.CancelledError:
                        pass
                    logger.info("Telegram token configuration changed; restarting bot")
                else:
                    changed.cancel()
                    try:
                        await changed
                    except asyncio.CancelledError:
                        pass
                    # Propagate failures to the retry handler below.
                    await running
                    logger.warning("Telegram polling stopped; retrying")
                for task in pending:
                    task.cancel()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Telegram bot stopped unexpectedly; retrying")
            try:
                await asyncio.wait_for(_configuration_changed.wait(), timeout=10.0)
            except TimeoutError:
                pass
