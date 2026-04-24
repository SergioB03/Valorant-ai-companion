import os
from pathlib import Path
from typing import AsyncIterator

import anthropic
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
async_client = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


def _build_analysis_prompt(match_summaries: list) -> str:
    matches_text = "\n".join([
        f"- {m['map']} | {m['agent']} | {m['kills']}/{m['deaths']}/{m['assists']} | HS%: {m['headshot_percent']} | {'Win' if m['won'] else 'Loss'}"
        for m in match_summaries
    ])

    return f"""You are an expert Valorant performance analyst and mental coach.

Here are the player's recent matches:
{matches_text}

Give a personalized analysis covering:
1. Performance patterns you notice
2. Strengths to build on
3. Areas to improve
4. One mental/tilt warning sign if any
5. One actionable tip for their next game

Keep it concise, direct and encouraging."""


def ask_claude(prompt: str) -> str:
    message = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=1000,
        messages=[
            {"role": "user", "content": prompt}
        ]
    )
    return message.content[0].text


def analyze_matches(match_summaries: list) -> str:
    return ask_claude(_build_analysis_prompt(match_summaries))


async def stream_analysis(match_summaries: list) -> AsyncIterator[str]:
    prompt = _build_analysis_prompt(match_summaries)
    async with async_client.messages.stream(
        model=CLAUDE_MODEL,
        max_tokens=1000,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        async for text in stream.text_stream:
            yield text
