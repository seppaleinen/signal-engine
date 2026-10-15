"""
Stage 4: The decision pass.

Implements the two-question routing from PROFILE.md:
  1. Relevance (score 0-1): Is this about practical AI-for-coding?
  2. Reports something new and concrete (yes/no)

Routing:
  drop   relevance < 0.4 OR new_score < 0.1
  keep   relevance >= 0.5 AND new_score >= 0.6
  unsure everything else (goes to reading pass)
"""

import os
import httpx
from typing import List, Dict, Tuple
from dotenv import load_dotenv

load_dotenv()

LITELLM_BASE = os.getenv("LITELLM_BASE_URL", "")
LITELLM_KEY = os.getenv("LITELLM_API_KEY", "")

# Only use real LLM if both URL and key are configured
USE_REAL_LLM = bool(LITELLM_BASE and LITELLM_KEY)

# Decision questions from PROFILE.md
QUESTIONS = {
    "relevance": {
        "instructions": "Is this about practical AI-for-coding — building systems with AI, optimizing AI workflows, or a new tool in that stack?",
        "criteria": [
            "Not about my area",
            "Peripheral to AI-coding",
            "About AI-coding in general",
            "Directly about AI-assisted coding workflows",
            "Directly changes how I work"
        ]
    },
    "new": {
        "instructions": "Does this report a specific, actionable finding (a release, a feature, a tool, a measured result, a technique, a documented incident)?",
        "criteria": {
            "true": "Yes: a release, feature, tool, measured result, technique, or documented incident",
            "false": "No: opinion, question, complaint, joke, reaction, rumor"
        }
    }
}

def build_prompt(item: Dict) -> str:
    """Build the state text for the decision model."""
    title = item.get("title", "")
    body = item.get("body", "")[:1500]
    url = item.get("url", "")
    return f"{title}\n\n{body}\n\n{url}"

async def decide_one(item: Dict) -> Dict:
    """
    Call the decision model for a single item.
    If LITELLM_BASE is not set, returns a mock decision for testing.
    """
    if not USE_REAL_LLM:
        # Mock decision for testing purposes
        # Heuristic based on keywords
        title_lower = item.get("title", "").lower()
        body_lower = item.get("body", "").lower()
        
        # Relevance heuristic
        relevance_score = 0.0
        if any(k in title_lower or k in body_lower for k in ["ai", "agent", "coding", "llm", "model", "release", "tool", "workflow", "quantization"]):
            relevance_score = 0.7
        elif any(k in title_lower or k in body_lower for k in ["github", "open", "lite"]):
            relevance_score = 0.5
        
        # Newness heuristic
        new_score = 0.0
        if any(k in title_lower for k in ["release", "v", "update", "new", "launch"]):
            new_score = 0.8
        elif any(k in body_lower for k in ["released", "announce", "how to", "technique", "optimization"]):
            new_score = 0.7
        else:
            new_score = 0.3
        
        return {
            "relevance": relevance_score,
            "new": new_score,
            "raw": None
        }
    
    # Real LLM call via LiteLLM
    # Using freellmapi which is available on the LiteLLM proxy
    payload = {
        "model": "freellmapi",
        "messages": [
            {"role": "system", "content": "You are a decision model. Respond with JSON only. No extra text."},
            {"role": "user", "content": f"Title: {item['title']}\n\nBody: {item.get('body','')[:1000]}\n\nURL: {item.get('url','')}\n\nRate relevance for practical AI-for-coding (0 to 1): {QUESTIONS['relevance']['instructions']}\nRate how new/concrete this is (0 to 1): {QUESTIONS['new']['instructions']}\n\nRespond with JSON only: {{\"relevance\": <float 0-1>, \"new\": <float 0-1>}}"}
        ]
    }
    
    headers = {}
    if LITELLM_KEY:
        headers["Authorization"] = f"Bearer {LITELLM_KEY}"
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(f"{LITELLM_BASE}/chat/completions", json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        # Parse JSON response
        import json as _json
        result = _json.loads(content)
        return {
            "relevance": float(result.get("relevance", 0)),
            "new": float(result.get("new", 0)),
            "raw": data
        }

def route_item(scores: Dict) -> str:
    """Route item based on scores."""
    relevance = scores.get("relevance", 0)
    new = scores.get("new", 0)
    
    if relevance < 0.4 or new < 0.1:
        return "drop"
    if relevance >= 0.5 and new >= 0.6:
        return "keep"
    return "unsure"

async def decide_batch(items: List[Dict]) -> List[Tuple[Dict, Dict, str]]:
    """
    Decide on a batch of items.
    Returns list of (item, scores, route)
    """
    import asyncio
    tasks = [decide_one(item) for item in items]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    out = []
    for item, result in zip(items, results):
        if isinstance(result, Exception):
            # On failure, route to unsure (never drop on error)
            scores = {"relevance": 0.5, "new": 0.5}
            route = "unsure"
        else:
            scores = result
            route = route_item(scores)
        out.append((item, scores, route))
    
    return out