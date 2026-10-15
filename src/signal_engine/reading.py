"""
Stage 5: The reading pass and digest generation.

Reads items that passed filters + decision pass, groups related items,
and writes a digest in the format from PROFILE.md.
"""

import os
import json
import asyncio
import httpx
from datetime import datetime
from pathlib import Path
from typing import List, Dict
from dotenv import load_dotenv

load_dotenv()

LITELLM_BASE = os.getenv("LITELLM_BASE_URL", "")
LITELLM_KEY = os.getenv("LITELLM_API_KEY", "")
USE_REAL_LLM = bool(LITELLM_BASE and LITELLM_KEY)

# From PROFILE.md
FOCUS = "practical AI-for-coding — building systems with AI, optimizing AI workflows, or a new tool in that stack"
DIGEST_CAP = 10
DIGEST_FORMAT = """# {date} - {headline}

## Releases & Updates
{items}

## Also worth a look
{also}
"""

DIGEST_PROMPT = f"""You write a daily digest for one person. They keep up with {FOCUS}, and they read this to decide what to try or adopt this week.

Below are today's items that passed their filter. Some are marked unsure: include one only if it clearly reports something new and concrete that matters to them.

Rules:
- At most {DIGEST_CAP} items. Pick the ones that change what they would do this week.
- Group items about the same thing into one entry.
- One or two plain sentences per entry: what changed, and why it matters to them.
- Keep every link. Never invent a link or a detail that is not in the item.
- Say plainly when something is a rumor, a minor update or a deprecation.
- A changelog entry is a launch only if it says something launched.
- No hype words, no exclamation marks.

Format:
# <Date> - <one line on what mattered today>

## <Group>
- **<Item in plain words>** - one or two sentences on what changed and why it matters. [source](url)

## Also worth a look
- one-liners with links

Items (JSON array with title, source, url, body, relevance, new, route):
{{items_json}}

Respond with markdown only. No extra text before or after.
"""

async def generate_digest(items: List[Dict], date_str: str | None = None) -> str:
    """
    Generate a digest from items that passed filters + decision pass.
    Items should be sorted by (route desc, relevance desc) - keeps first, then unsure by relevance.
    """
    if not items:
        return f"# {date_str or datetime.now().strftime('%Y-%m-%d')}\n\nNo items to digest today.\n"
    
    # Prepare items for the prompt
    items_for_prompt = []
    for item in items[:DIGEST_CAP * 2]:  # Give LLM some extra to choose from
        items_for_prompt.append({
            "title": item.get("title", ""),
            "source": item.get("source", ""),
            "url": item.get("url", ""),
            "body": item.get("body", "")[:300],
            "relevance": item.get("decision", {}).get("relevance", 0),
            "new": item.get("decision", {}).get("new", 0),
            "route": item.get("decision", {}).get("route", "unsure")
        })
    
    prompt = DIGEST_PROMPT.format(items_json=json.dumps(items_for_prompt, indent=2))
    
    if not USE_REAL_LLM:
        # Mock digest for testing
        headline = f"{len(items)} items passed filters"
        items_md = "\n".join([
            f"- **{item.get('title', 'Untitled')}** - {item.get('source', 'unknown')} [{item.get('route', 'unknown')}]. [link]({item.get('url', '#')})"
            for item in items[:DIGEST_CAP]
        ])
        return f"# {date_str or datetime.now().strftime('%Y-%m-%d')} - {headline}\n\n## Releases & Updates\n{items_md}\n"
    
    # Real LLM call
    payload = {
        "model": "freellmapi",
        "messages": [
            {"role": "system", "content": "You write digests. Respond with markdown only. No extra text."},
            {"role": "user", "content": prompt}
        ]
    }
    
    headers = {}
    if LITELLM_KEY:
        headers["Authorization"] = f"Bearer {LITELLM_KEY}"
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(f"{LITELLM_BASE}/chat/completions", json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        return content.strip()

def write_digest(digest: str, date_str: str | None = None, digest_dir: str = "digests") -> Path:
    """Write digest to file. Returns the path."""
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")
    
    digest_path = Path(digest_dir) / f"{date_str}.md"
    digest_path.parent.mkdir(parents=True, exist_ok=True)
    digest_path.write_text(digest, encoding="utf-8")
    return digest_path