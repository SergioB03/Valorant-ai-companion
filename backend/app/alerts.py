import logging
import os
import threading
import time
import traceback

import httpx

logger = logging.getLogger(__name__)

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")

# Dedupe window so a repeated crash doesn't spam the channel.
_ALERT_WINDOW_SECONDS = 600
_recent_alerts: dict = {}
_lock = threading.Lock()


def _should_send(key: str) -> bool:
    now = time.monotonic()
    with _lock:
        last = _recent_alerts.get(key)
        if last is not None and now - last < _ALERT_WINDOW_SECONDS:
            return False
        _recent_alerts[key] = now
        return True


def _post(payload: dict):
    try:
        httpx.post(DISCORD_WEBHOOK_URL, json=payload, timeout=5.0)
    except Exception:
        logger.warning("Failed to deliver Discord error alert", exc_info=True)


def notify_error(context: str, exc: Exception):
    """Fire-and-forget Discord alert for an unexpected server error.

    No-op unless DISCORD_WEBHOOK_URL is set. Never raises.
    """
    if not DISCORD_WEBHOOK_URL:
        return
    key = f"{context}:{type(exc).__name__}"
    if not _should_send(key):
        return
    tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))[-900:]
    payload = {
        "embeds": [{
            "title": f"🚨 Backend error: {type(exc).__name__}",
            "description": f"**Where:** `{context}`\n**Error:** {str(exc)[:200] or '(no message)'}\n```py\n{tb}\n```",
            "color": 0xFF4655,
        }]
    }
    threading.Thread(target=_post, args=(payload,), daemon=True).start()
