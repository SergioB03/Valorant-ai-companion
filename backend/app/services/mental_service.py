import json
from statistics import mean
from app.services.claude_service import ask_claude

RECOMMENDATIONS = {
    "calm": "Green light — queue up.",
    "warming": "Play one more, then re-evaluate.",
    "heated": "Take a 30-minute break before your next queue.",
    "tilted": "Stop for today. Protect your MMR and your mental.",
}


def _kda(match: dict) -> float:
    kills = match.get("kills") or 0
    deaths = match.get("deaths") or 0
    assists = match.get("assists") or 0
    return (kills + assists) / max(1, deaths)


def _tilt_level(score: int) -> str:
    if score <= 24:
        return "calm"
    if score <= 49:
        return "warming"
    if score <= 74:
        return "heated"
    return "tilted"


def detect_tilt(summaries: list, game_name: str, tag_line: str) -> dict:
    riot_id = f"{game_name}#{tag_line}".lower()
    n = len(summaries)
    signals = []
    score = 0

    # loss streak (summaries are newest first)
    loss_streak = 0
    for m in summaries:
        if m.get("won"):
            break
        loss_streak += 1
    if loss_streak >= 4:
        score += 35
        signals.append({"type": "loss_streak", "severity": "critical", "detail": f"{loss_streak} losses in a row"})
    elif loss_streak == 3:
        score += 25
        signals.append({"type": "loss_streak", "severity": "high", "detail": "3 losses in a row"})
    elif loss_streak == 2:
        score += 15
        signals.append({"type": "loss_streak", "severity": "medium", "detail": "2 losses in a row"})

    # recent-vs-baseline trends (need at least 5 games)
    kda_recent = kda_baseline = None
    hs_recent = hs_baseline = None
    if n >= 5:
        recent, rest = summaries[:3], summaries[3:]

        raw_kda_recent = mean(_kda(m) for m in recent)
        raw_kda_baseline = mean(_kda(m) for m in rest)
        kda_recent = round(raw_kda_recent, 2)
        kda_baseline = round(raw_kda_baseline, 2)
        if raw_kda_baseline > 0:
            drop = (raw_kda_baseline - raw_kda_recent) / raw_kda_baseline
            if drop > 0.5:
                score += 30
                signals.append({
                    "type": "kda_drop", "severity": "high",
                    "detail": f"KDA down {round(drop * 100)}% vs baseline ({kda_recent} vs {kda_baseline})",
                })
            elif drop > 0.3:
                score += 20
                signals.append({
                    "type": "kda_drop", "severity": "medium",
                    "detail": f"KDA down {round(drop * 100)}% vs baseline ({kda_recent} vs {kda_baseline})",
                })

        raw_hs_recent = mean((m.get("headshot_percent") or 0) for m in recent)
        raw_hs_baseline = mean((m.get("headshot_percent") or 0) for m in rest)
        hs_recent = round(raw_hs_recent, 1)
        hs_baseline = round(raw_hs_baseline, 1)
        if raw_hs_baseline > 0:
            drop = (raw_hs_baseline - raw_hs_recent) / raw_hs_baseline
            if drop > 0.4:
                score += 15
                signals.append({
                    "type": "hs_drop", "severity": "medium",
                    "detail": f"Headshot% down {round(drop * 100)}% vs baseline ({hs_recent}% vs {hs_baseline}%)",
                })
            elif drop > 0.25:
                score += 10
                signals.append({
                    "type": "hs_drop", "severity": "low",
                    "detail": f"Headshot% down {round(drop * 100)}% vs baseline ({hs_recent}% vs {hs_baseline}%)",
                })

        wins = sum(1 for m in summaries if m.get("won"))
        win_rate = wins / n
        if win_rate < 0.4:
            score += 10
            signals.append({
                "type": "low_win_rate", "severity": "low",
                "detail": f"Win rate {round(win_rate * 100)}% over last {n} matches",
            })

    # trigger maps/agents: 2+ games with 0 wins
    map_stats: dict = {}
    agent_stats: dict = {}
    for m in summaries:
        for key, stats in ((m.get("map"), map_stats), (m.get("agent"), agent_stats)):
            if not key:
                continue
            entry = stats.setdefault(key, {"games": 0, "wins": 0})
            entry["games"] += 1
            entry["wins"] += 1 if m.get("won") else 0
    trigger_maps = [k for k, v in map_stats.items() if v["games"] >= 2 and v["wins"] == 0]
    trigger_agents = [k for k, v in agent_stats.items() if v["games"] >= 2 and v["wins"] == 0]
    score += min(5 * (len(trigger_maps) + len(trigger_agents)), 10)
    if trigger_maps:
        signals.append({"type": "trigger_map", "severity": "low", "detail": f"0 wins on: {', '.join(trigger_maps)}"})
    if trigger_agents:
        signals.append({"type": "trigger_agent", "severity": "low", "detail": f"0 wins as: {', '.join(trigger_agents)}"})

    tilt_score = max(0, min(100, score))
    tilt_level = _tilt_level(tilt_score)

    return {
        "riot_id": riot_id,
        "matches_analyzed": n,
        "tilt_score": tilt_score,
        "tilt_level": tilt_level,
        "current_loss_streak": loss_streak,
        "signals": signals,
        "kda_trend": {"recent": kda_recent, "baseline": kda_baseline},
        "hs_trend": {"recent": hs_recent, "baseline": hs_baseline},
        "triggers": {"maps": trigger_maps, "agents": trigger_agents},
        "recommendation": RECOMMENDATIONS[tilt_level],
    }


def _snapshots_text(snapshots: list) -> str:
    lines = [
        f"- {s.get('created_at')}: tilt {s.get('tilt_score')} ({s.get('tilt_level')}) over {s.get('matches_analyzed')} matches"
        for s in snapshots[:5]
    ]
    return "\n".join(lines) if lines else "No previous snapshots."


def generate_coach_message(report: dict, history: list) -> str:
    system = (
        "You are a supportive but honest Valorant mental performance coach. "
        "Speak directly to the player in second person. Reference the specific signals in their tilt report, "
        "acknowledge what is going well, and give one concrete next step. "
        "Plain text only, no headers or bullet lists, under 120 words."
    )
    prompt = f"""Current tilt report:
{json.dumps(report, indent=2)}

Recent tilt snapshot history (newest first):
{_snapshots_text(history)}

Give the player a short coach message about where their head is at right now and what to do next."""
    return ask_claude(prompt, system=system)


def coach_chat(riot_id: str, user_message: str, report: dict | None, snapshots: list, history: list) -> str:
    """`history` is the client's own conversation (CoachTurn: role/text), not
    stored rows — see CoachRequest.history in routes/mental.py for why."""
    system = (
        "You are a supportive but honest Valorant mental performance coach chatting with a player. "
        "Use their latest tilt data and the previous conversation as context. Be specific, practical, "
        "and encouraging without sugarcoating. Plain text only, 150 words max."
    )
    tilt_context = json.dumps(report, indent=2) if report else "No fresh match data available right now."
    turns = [
        f"{'Player' if t.role == 'user' else 'Coach'}: {t.text}"
        for t in history[-10:]
    ]
    conversation = "\n".join(turns) if turns else "No previous conversation."
    prompt = f"""Player: {riot_id}

Latest tilt report:
{tilt_context}

Recent tilt snapshots (newest first):
{_snapshots_text(snapshots)}

Previous conversation:
{conversation}

Player's new message:
{user_message}

Reply as their coach."""
    return ask_claude(prompt, system=system)
