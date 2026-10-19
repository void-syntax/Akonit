"""Custom Prometheus metrics for Akonit Signal Radar.

Defines all requested metrics:
- signals_ingested_total (Counter) - labeled by source
- signals_noise_filtered_total (Counter)
- laya_classification_duration_seconds (Histogram)
- pipeline_cycle_duration_seconds (Histogram)
- active_websocket_connections (Gauge)
- cache_hits_total (Counter)
- cache_misses_total (Counter)
- dlq_size (Gauge)
"""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

signals_ingested_total = Counter(
    "signals_ingested_total",
    "Total signals ingested successfully",
    ["source_id"],
)

signals_noise_filtered_total = Counter(
    "signals_noise_filtered_total",
    "Total signals filtered as noise or thin content",
    ["reason"],
)

laya_classification_duration_seconds = Histogram(
    "laya_classification_duration_seconds",
    "Laya AI classification latency in seconds",
)

pipeline_cycle_duration_seconds = Histogram(
    "pipeline_cycle_duration_seconds",
    "Full ingestion cycle duration in seconds",
)

active_websocket_connections = Gauge(
    "active_websocket_connections",
    "Live WebSocket or SSE/stream client count",
)

cache_hits_total = Counter(
    "cache_hits_total",
    "Total cache hits",
)

cache_misses_total = Counter(
    "cache_misses_total",
    "Total cache misses",
)

dlq_size = Gauge(
    "dlq_size",
    "Current items in Dead Letter Queue",
)
