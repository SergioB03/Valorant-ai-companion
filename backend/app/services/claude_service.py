import os
import anthropic
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

def ask_claude(prompt: str) -> str:
    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1000,
        messages=[
            {"role": "user", "content": prompt}
        ]
    )
    return message.content[0].text

def analyze_matches(match_summaries: list) -> str:
    matches_text = "\n".join([
        f"- {m['map']} | {m['agent']} | {m['kills']}/{m['deaths']}/{m['assists']} | HS%: {m['headshot_percent']} | {'Win' if m['won'] else 'Loss'}"
        for m in match_summaries
    ])
    
    prompt = f"""You are an expert Valorant performance analyst and mental coach.
    
Here are the player's recent matches:
{matches_text}

Give a personalized analysis covering:
1. Performance patterns you notice
2. Strengths to build on
3. Areas to improve
4. One mental/tilt warning sign if any
5. One actionable tip for their next game

Keep it concise, direct and encouraging."""

    return ask_claude(prompt)