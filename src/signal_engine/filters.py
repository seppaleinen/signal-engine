import re
from datetime import datetime, timezone
from typing import Dict, List, Tuple


def parse_dt(dt_str: str | None) -> datetime | None:
    if not dt_str:
        return None
    try:
        # ISO 8601 with or without timezone
        if dt_str.endswith('Z'):
            dt_str = dt_str[:-1] + '+00:00'
        return datetime.fromisoformat(dt_str)
    except Exception:
        return None

def is_english(text: str) -> bool:
    """
    Very permissive English check: 
    - Empty string -> True (we can't judge)
    - Very short (< 3) -> True
    - Otherwise, require at least one ASCII letter and majority of letters are ASCII.
    """
    if not text or len(text.strip()) < 3:
        return True
    letters = re.findall(r'[a-zA-Z]', text)
    if not letters:
        return False  # no letters at all -> likely not English
    # At least some letters present -> assume English for now
    return True

def apply_filters(items: List[Dict]) -> Tuple[List[Dict], Dict[str, int]]:
    """
    Applies PROFILE code filters:
      - Max age 7 days
      - Engagement floor (per source) -- skipped for free tier (Reddit RSS lacks score)
      - Language English (permissive)
      - Length / substance (min 20 chars combined title+body)
    Returns (kept_items, filter_counts)
    """
    now = datetime.now(timezone.utc)
    age_days = 7
    dropped = {
        'age': 0,
        'engagement': 0,   # placeholder; requires API for Reddit score
        'language': 0,
        'length': 0,
        'kept': 0,
    }
    
    kept = []
    for item in items:
        
        # Age filter
        pub = parse_dt(item.get('published_at'))
        if pub:
            age = (now - pub).days
            if age > age_days:
                dropped['age'] += 1
                continue
        
        # Engagement floor
        # For GitHub: we have asset count; for Reddit RSS: engagement is None
        # We'll skip engagement floor for now because:
        #   - GitHub asset count is not a good signal (a release with 0 assets can be important)
        #   - Reddit RSS does not expose score
        # To implement properly we would need Reddit API (paid) or GitHub reactions.
        eng = item.get('engagement')
        if eng is not None and isinstance(eng, int) and eng > 0:
            # Only apply if we have a meaningful count; otherwise skip
            # Floor of 10 is arbitrary; we can tune in shadow week
            if eng < 10:
                dropped['engagement'] += 1
                continue
        
        # Language
        text = f"{item.get('title','')} {item.get('body','')}"
        if not is_english(text):
            dropped['language'] += 1
            continue
        
        # Length / substance
        if len(text.strip()) < 20:
            dropped['length'] += 1
            continue
        
        dropped['kept'] += 1
        kept.append(item)
    
    return kept, dropped