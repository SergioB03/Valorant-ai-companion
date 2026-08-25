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


def _should_send(key: str, window: int = _ALERT_WINDOW_SECONDS) -> bool:
    now = time.monotonic()
    with _lock:
        last = _recent_alerts.get(key)
        if last is not None and now - last < window:
            return False
        # Bound the dict: without this it grows one entry per distinct alert key
        # forever, and an IP-rotating attacker could make that unbounded on a
        # 2 GB box. Expired entries can never suppress anything, so drop them.
        if len(_recent_alerts) > 500:
            cutoff = now - max(window, _ALERT_WINDOW_SECONDS)
            for k in [k for k, t in _recent_alerts.items() if t < cutoff]:
                del _recent_alerts[k]
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


# Severity colours for notify_alert.
WARN = 0xFACC15   # heads-up: still working, but heading somewhere bad
DOWN = 0xFB923C   # a feature is off right now


def notify_alert(title: str, body: str, key: str, window: int = 3600,
                 color: int = WARN) -> None:
    """Alert the operator about an *expected* condition, not a crash.

    notify_error only fires for unhandled exceptions, which meant every failure
    mode the app deliberately handles — budget exhausted, upstream key rejected,
    rate limits saturated — announced itself only to a log file inside a
    container nobody tails. Those are precisely the conditions worth knowing
    about: the app keeps answering requests while a feature is quietly dead.

    `window` is the dedupe period in seconds; defaults to an hour because these
    conditions persist and would otherwise repeat on every request.
    No-op unless DISCORD_WEBHOOK_URL is set. Never raises.
    """
    if not DISCORD_WEBHOOK_URL:
        return
    if not _should_send(key, window):
        return
    payload = {"embeds": [{"title": title, "description": body[:1800], "color": color}]}
    threading.Thread(target=_post, args=(payload,), daemon=True).start()
