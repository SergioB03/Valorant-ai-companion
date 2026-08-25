import json
import os
import anthropic
from dotenv import load_dotenv
from pathlib import Path

from app.budget import check_budget, record_spend

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-opus-4-8")

# Bounded so a slow/hung call fails cleanly inside the proxy's 60 s origin timeout (see
# DEPLOYMENT.md) instead of surfacing as a gateway error — and is never silently retried
# (and billed) a second time. Transient 429/529s surface to the user, who can retry.
client = anthropic.Anthropic(
    api_key=os.getenv("ANTHROPIC_API_KEY"),
    timeout=float(os.getenv("CLAUDE_TIMEOUT_SECONDS", "50")),
    max_retries=0,
)


def _create(**kwargs):
    """Every Claude call in this app goes through here.

    Routing all of them past one function is the point: the daily budget check
    and the spend accounting cannot be forgotten on a new endpoint the way a
    per-route decorator can (which is exactly how /meta/ask ended up with no
    cost ceiling at all).
    """
    check_budget()
    message = client.messages.create(**kwargs)
    usage = getattr(message, "usage", None)
    if usage is not None:
        record_spend(
            kwargs.get("model", CLAUDE_MODEL),
            getattr(usage, "input_tokens", 0) or 0,
            getattr(usage, "output_tokens", 0) or 0,
        )
    return message

def ask_claude(prompt: str, system: str | None = None, max_tokens: int = 4000) -> str:
    kwargs = {}
    if system:
        kwargs["system"] = system
    message = _create(
        model=CLAUDE_MODEL,
        max_tokens=max_tokens,
        thinking={"type": "adaptive"},
        messages=[
            {"role": "user", "content": prompt}
        ],
        **kwargs,
    )
    text = next((block.text for block in message.content if block.type == "text"), "")
    if not text and message.stop_reason == "max_tokens":
        raise RuntimeError("Claude hit the token limit before producing text")
    return text

def analyze_matches(match_summaries: list) -> str:
    matches_text = "\n".join([
        f"- {m['map']} | {m['agent']} | {m['kills']}/{m['deaths']}/{m['assists']} | HS%: {m['headshot_percent']} | {'Win' if m['won'] else 'Loss'}"
        for m in match_summaries
    ])

    prompt = f"""You are an expert Valorant performance analyst and mental coach.

Here are the player's recent matches (newest first):
{matches_text}

Give a personalized analysis covering:
1. Performance patterns you notice
2. Strengths to build on
3. Areas to improve
4. One mental/tilt warning sign if any
5. One actionable tip for their next game

Keep it concise, direct and encouraging.
Plain text only — no markdown headers, asterisks, or bullet syntax. Use short paragraphs and numbered lines like '1.' at most."""

    return ask_claude(prompt)

ANALYSIS_SCHEMA = {
    "type": "object",
    "properties": {
        "overview": {"type": "string"},
        "strengths": {"type": "array", "items": {"type": "string"}},
        "weaknesses": {"type": "array", "items": {"type": "string"}},
        "tilt_warning": {"type": ["string", "null"]},
        "tip": {"type": "string"},
    },
    "required": ["overview", "strengths", "weaknesses", "tilt_warning", "tip"],
    "additionalProperties": False,
}

def analyze_matches_structured(match_summaries: list) -> dict:
    matches_text = "\n".join([
        f"- {m['map']} | {m['agent']} | {m['kills']}/{m['deaths']}/{m['assists']} | HS%: {m['headshot_percent']} | {'Win' if m['won'] else 'Loss'}"
        for m in match_summaries
    ])

    prompt = f"""You are an expert Valorant performance analyst and mental coach.

Here are the player's recent matches (newest first):
{matches_text}

Produce a personalized analysis as JSON with these fields:
- overview: a 2-3 sentence read of how the player is doing right now
- strengths: a list of short strengths to build on (2-4 items)
- weaknesses: a list of short areas to improve (2-4 items)
- tilt_warning: one mental/tilt warning sign if you see one, otherwise null
- tip: one concrete, actionable tip for their next game

Keep every item concise, direct and encouraging. Plain text only inside each string — no markdown."""

    message = _create(
        model=CLAUDE_MODEL,
        max_tokens=4000,
        thinking={"type": "adaptive"},
        output_config={"format": {"type": "json_schema", "schema": ANALYSIS_SCHEMA}},
        messages=[
            {"role": "user", "content": prompt}
        ],
    )
    text = next((block.text for block in message.content if block.type == "text"), "")
    if not text and message.stop_reason == "max_tokens":
        raise RuntimeError("Claude hit the token limit before producing the analysis")
    return json.loads(text)
