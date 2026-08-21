from statistics import mean
from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from app.errors import upstream_to_http
from app.limiter import limiter
from app.services.riot_service import get_match_history, summarize_matches
from app.services.mental_service import detect_tilt, generate_coach_message, coach_chat
from app.db import save_snapshot, get_snapshots, save_session, get_sessions

router = APIRouter(prefix="/mental", tags=["mental"])

class CoachRequest(BaseModel):
    game_name: str
    tag_line: str
    region: str = "na"
    message: str


def _filter_mode(summaries: list, mode: str | None) -> list:
    if not mode:
        return summaries
    return [m for m in summaries if (m.get("mode") or "").lower() == mode.lower()]


def _tilt_check_sync(raw: dict, game_name: str, tag_line: str, mode: str | None = None) -> dict:
    summaries = _filter_mode(summarize_matches(raw, game_name, tag_line), mode)
    if not summaries:
        raise HTTPException(status_code=404, detail="No matches found for that name/tag")
    report = detect_tilt(summaries, game_name, tag_line)
    history = get_snapshots(report["riot_id"], limit=5)
    try:
        coach_message = generate_coach_message(report, history)
    except Exception as e:
        # Still persist the tilt report even if the Claude call failed.
        save_snapshot(report["riot_id"], report)
        notify_error("mental.tilt_check.coach_message", e)
        raise HTTPException(status_code=502, detail="Coach message generation failed; tilt report was saved.")
    report["coach_message"] = coach_message
    save_snapshot(report["riot_id"], report)
    return report


@router.get("/tilt-check/{game_name}/{tag_line}")
@limiter.limit("10/minute")
async def tilt_check(request: Request, game_name: str, tag_line: str, region: str = "na", size: int = 10, mode: str = "competitive"):
    try:
        raw = await get_match_history(game_name, tag_line, region, size, mode=mode or None)
        return await run_in_threadpool(_tilt_check_sync, raw, game_name, tag_line, mode or None)
    except HTTPException:
        raise
    except Exception as e:
        raise upstream_to_http(e, "mental.tilt_check")


def _coach_sync(raw: dict | None, request: CoachRequest, riot_id: str) -> dict:
    report = None
    if raw is not None:
        try:
            summaries = _filter_mode(summarize_matches(raw, request.game_name, request.tag_line), "competitive")
            if summaries:
                report = detect_tilt(summaries, request.game_name, request.tag_line)
        except Exception:
            report = None
    snapshots = get_snapshots(riot_id, limit=5)
    sessions = get_sessions(riot_id, limit=5)
    reply = coach_chat(riot_id, request.message, report, snapshots, sessions)
    save_session(riot_id, request.message, reply)
    return {
        "reply": reply,
        "tilt_score": report["tilt_score"] if report else None,
        "tilt_level": report["tilt_level"] if report else None,
    }


@router.post("/coach")
@limiter.limit("15/minute")
async def coach(request: Request, body: CoachRequest):
    riot_id = f"{body.game_name}#{body.tag_line}".lower()
    raw = None
    try:
        raw = await get_match_history(body.game_name, body.tag_line, body.region, 10, mode="competitive")
    except Exception:
        raw = None
    try:
        return await run_in_threadpool(_coach_sync, raw, body, riot_id)
    except HTTPException:
        raise
    except Exception as e:
        raise upstream_to_http(e, "mental.coach")


@router.get("/profile/{game_name}/{tag_line}")
def profile(game_name: str, tag_line: str):
    riot_id = f"{game_name}#{tag_line}".lower()
    snapshots = get_snapshots(riot_id)
    sessions = get_sessions(riot_id)
    if len(snapshots) >= 6:
        newest = mean(s["tilt_score"] for s in snapshots[:3])
        oldest = mean(s["tilt_score"] for s in snapshots[-3:])
    elif len(snapshots) >= 2:
        newest = snapshots[0]["tilt_score"]
        oldest = snapshots[-1]["tilt_score"]
    else:
        return {"riot_id": riot_id, "snapshots": snapshots, "sessions": sessions, "trend": "insufficient_data"}
    if newest <= oldest - 10:
        trend = "improving"
    elif newest >= oldest + 10:
        trend = "worsening"
    else:
        trend = "stable"
    return {"riot_id": riot_id, "snapshots": snapshots, "sessions": sessions, "trend": trend}
