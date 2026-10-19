"""Structured logging setup with OpenTelemetry trace_id integration."""

from __future__ import annotations

import logging
import sys
from opentelemetry import trace


class TraceIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            span = trace.get_current_span()
            ctx = span.get_span_context()
            if ctx.is_valid:
                record.trace_id = format(ctx.trace_id, "032x")
            else:
                record.trace_id = "00000000000000000000000000000000"
        except Exception:
            record.trace_id = "00000000000000000000000000000000"
        return True


def setup_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(TraceIdFilter())
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s | %(levelname)-7s | trace=%(trace_id)s | %(name)-28s | %(message)s",
            datefmt="%H:%M:%S",
        )
    )
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    for noisy in ("httpx", "httpcore", "apscheduler", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


setup_logging()
