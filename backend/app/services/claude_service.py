import os
import anthropic
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-opus-4-8")

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

def ask_claude(prompt: str, system: str | None = None, max_tokens: int = 4000) -> str:
    kwargs = {}
    if system:
        kwargs["system"] = system
    message = client.messages.create(
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
