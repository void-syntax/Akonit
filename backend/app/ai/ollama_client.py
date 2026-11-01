"""Robust Ollama Local AI Classifier Service (`backend/app/ai/ollama_client.py`).

Communicates with a local Ollama instance (e.g. Qwen3 4B) using native JSON schema
enforcement and structured Pydantic models. Falls back gracefully when Ollama
is offline or unreachable.
"""

from __future__ import annotations

import httpx
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("app.ai.ollama_client")


class SignalEvaluation(BaseModel):
    priority: str = Field(description="Priority level: critical, watch, or normal")
    priority_score: float = Field(description="Numerical score between 0.0 and 1.0")
    category: str = Field(description="Assigned category (e.g. AI, Crypto, Security, Tech)")
    should_notify: float = Field(description="Notification probability between 0.0 and 1.0")
    noise_probability: float = Field(description="Probability that this signal is spam or noise between 0.0 and 1.0")
    trending_score: float = Field(description="Trending momentum score between 0.0 and 1.0")


async def evaluate_signal_with_ollama(
    *,
    title: str,
    description: str,
    source_id: str,
    growth: float,
    strength: float,
    status: str,
) -> dict[str, Any] | None:
    """Evaluate a signal using local Ollama instance with structured JSON output."""
    if not getattr(settings, "ollama_enabled", False):
        return None

    base_url = getattr(settings, "ollama_base_url", "http://localhost:11434")
    model_name = getattr(settings, "ollama_model", "qwen3:4b")

    prompt = (
        f"Analyze this signal for tech/crypto trends radar:\n"
        f"Title: {title}\n"
        f"Description: {description}\n"
        f"Source: {source_id}\n"
        f"Growth rate: {growth:.2f}, Strength: {strength:.2f}, Status: {status}\n\n"
        f"Evaluate its priority (critical/watch/normal), category, noise probability, and trending score."
    )

    schema = SignalEvaluation.model_json_schema()

    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": "You are a precise signal intelligence evaluator. Respond strictly in JSON matching the requested schema."},
            {"role": "user", "content": prompt},
        ],
        "format": schema,
        "stream": False,
        "options": {
            "temperature": 0.1,
            "num_ctx": 2048,
        },
    }

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(f"{base_url}/api/chat", json=payload)
            if response.status_code != 200:
                logger.debug("Ollama returned status %d", response.status_code)
                return None
            data = response.json()
            content = data.get("message", {}).get("content", "{}")
            import json
            parsed = json.loads(content)
            # Validate with Pydantic
            validated = SignalEvaluation(**parsed)
            return {
                "priority": validated.priority,
                "priority_score": validated.priority_score,
                "category": validated.category,
                "should_notify": validated.should_notify,
                "noise_probability": validated.noise_probability,
                "trending_score": validated.trending_score,
                "model_used": model_name,
            }
    except Exception as exc:
        logger.debug("Ollama evaluation unavailable or failed: %r", exc)
        return None
