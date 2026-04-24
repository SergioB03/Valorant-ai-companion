from collections import Counter
from statistics import mean
from typing import AsyncIterator

from app.services.claude_service import ask_claude, stream_claude


def _kda(match: dict) -> float:
    deaths = match.get("deaths") or 0
    kills = match.get("kills") or 0
    assists = match.get("assists") or 0
    return (kills + assists) / deaths if deaths > 0 else float(kills + assists)


def _tilt_score(
    loss_streak: int,
    win_rate: float,
    kda_delta_pct: float | None,
    hs_delta_pct: float | None,
) -> int:
    score = 0
    score += min(loss_streak * 10, 40)
    if win_rate < 0.3:
        score += 20
    elif win_rate < 0.5:
        score += 10
    if kda_delta_pct is not None and kda_delta_pct < -20:
        score += 20
        if kda_delta_pct < -40:
            score += 10
    if hs_delta_pct is not None and hs_delta_pct < -20:
        score += 10
    return min(score, 100)


def detect_tilt_signals(matches: list) -> dict:
    """
    Deterministic tilt-pattern detection over match summaries (newest first).
    Returns structured signals consumed by the coach prompt.
    """
    if not matches:
        return {"has_data": False, "match_count": 0}

    total = len(matches)
    wins = sum(1 for m in matches if m.get("won"))
    win_rate = wins / total

    loss_streak = 0
    for m in matches:
        if not m.get("won"):
            loss_streak += 1
        else:
            break

    mid = total // 2
    recent = matches[:mid] if mid else []
    prior = matches[mid:] if mid else []

    kda_trend = None
    if recent and prior:
        recent_kda = mean(_kda(m) for m in recent)
        prior_kda = mean(_kda(m) for m in prior)
        delta_pct = ((recent_kda - prior_kda) / prior_kda * 100) if prior_kda > 0 else 0.0
        kda_trend = {
            "recent": round(recent_kda, 2),
            "prior": round(prior_kda, 2),
            "delta_pct": round(delta_pct, 1),
        }

    hs_trend = None
    if recent and prior:
        recent_hs = mean(m.get("headshot_percent", 0) or 0 for m in recent)
        prior_hs = mean(m.get("headshot_percent", 0) or 0 for m in prior)
        delta_pct = ((recent_hs - prior_hs) / prior_hs * 100) if prior_hs > 0 else 0.0
        hs_trend = {
            "recent": round(recent_hs, 1),
            "prior": round(prior_hs, 1),
            "delta_pct": round(delta_pct, 1),
        }

    losses_by_map = Counter(m["map"] for m in matches if not m.get("won") and m.get("map"))
    most_lost_map = None
    if losses_by_map:
        name, count = losses_by_map.most_common(1)[0]
        most_lost_map = {"map": name, "losses": count}

    losses_by_agent = Counter(m["agent"] for m in matches if not m.get("won") and m.get("agent"))
    most_lost_agent = None
    if losses_by_agent:
        name, count = losses_by_agent.most_common(1)[0]
        most_lost_agent = {"agent": name, "losses": count}

    tilt_score = _tilt_score(
        loss_streak,
        win_rate,
        kda_trend["delta_pct"] if kda_trend else None,
        hs_trend["delta_pct"] if hs_trend else None,
    )

    return {
        "has_data": True,
        "match_count": total,
        "win_rate": round(win_rate, 2),
        "loss_streak": loss_streak,
        "kda_trend": kda_trend,
        "headshot_trend": hs_trend,
        "most_lost_map": most_lost_map,
        "most_lost_agent": most_lost_agent,
        "tilt_score": tilt_score,
    }


def _build_coach_prompt(matches: list, signals: dict) -> str:
    match_log = "\n".join(
        f"- {m.get('map')} | {m.get('agent')} | {m.get('kills')}/{m.get('deaths')}/{m.get('assists')} | HS%: {m.get('headshot_percent')} | {'Win' if m.get('won') else 'Loss'}"
        for m in matches
    )

    kda_line = (
        f"{signals['kda_trend']['recent']} recent vs {signals['kda_trend']['prior']} earlier "
        f"({signals['kda_trend']['delta_pct']:+.1f}%)"
        if signals.get("kda_trend") else "not enough data"
    )
    hs_line = (
        f"{signals['headshot_trend']['delta_pct']:+.1f}% change"
        if signals.get("headshot_trend") else "not enough data"
    )
    map_line = (
        f"{signals['most_lost_map']['map']} ({signals['most_lost_map']['losses']} losses)"
        if signals.get("most_lost_map") else "none"
    )
    agent_line = (
        f"{signals['most_lost_agent']['agent']} ({signals['most_lost_agent']['losses']} losses)"
        if signals.get("most_lost_agent") else "none"
    )

    return f"""You are a supportive Valorant mental coach. Your job is to read tilt signals from a player's recent matches and help them reset — not just optimize stats, but preserve their love of the game.

Signals from the last {signals['match_count']} matches:
- Win rate: {int(signals['win_rate'] * 100)}%
- Current loss streak: {signals['loss_streak']} games
- KDA trend: {kda_line}
- Headshot trend: {hs_line}
- Map with most losses: {map_line}
- Agent with most losses: {agent_line}
- Tilt severity (0-100): {signals['tilt_score']}

Raw match log (most recent first):
{match_log}

Write a personalized mental coaching response in 5 short sections:

1. **What's going on** — one sentence naming what you see mentally (not just stats)
2. **Why this might be happening** — one sentence of gentle framing (don't lecture)
3. **One mental reset** — a concrete 60-second exercise they can do before next queue
4. **One in-game tweak** — a small tactical adjustment to reduce pressure (not a mechanical fix)
5. **Queue advice** — should they queue again, take a break, or stop for today? Say why.

Tone: honest, human, warm. Like a friend who plays the game, not a therapist reciting scripts. No platitudes. Don't just recite numbers back to them — interpret what the numbers mean for their headspace."""


def coach(matches: list, signals: dict) -> str:
    return ask_claude(_build_coach_prompt(matches, signals))


async def stream_coach(matches: list, signals: dict) -> AsyncIterator[str]:
    async for text in stream_claude(_build_coach_prompt(matches, signals)):
        yield text
