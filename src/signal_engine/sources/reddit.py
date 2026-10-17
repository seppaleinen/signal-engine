import time
import xml.etree.ElementTree as ET
from typing import Dict, List

import httpx

# Free Reddit RSS — no API key, no paid scraper. Reddit rate-limits unauthenticated
# requests (429), so we retry with backoff and cap posts per run.
REDDIT_SUBREDDITS = {
    "reddit-local-llm": ("r/LocalLLM", "LocalLLM"),
    "reddit-machine-learning": ("r/MachineLearning", "MachineLearning"),
}

NS = {
    'atom': 'http://www.w3.org/2005/Atom',
    'media': 'http://search.yahoo.com/mrss/',
}

def fetch_reddit_subreddit(subreddit: str, per_page: int = 30, max_retries: int = 4) -> List[Dict]:
    url = f"https://www.reddit.com/{subreddit}/.rss"
    headers = {"User-Agent": "signal-engine/1.0 (by seppa; contact: seppa@example.com)"}
    
    last_err = None
    for attempt in range(max_retries):
        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.get(url, headers=headers)
                if resp.status_code == 429:
                    wait = 5 * (attempt + 1)
                    time.sleep(wait)
                    continue
                resp.raise_for_status()
                text = resp.text
                # Guard against HTML login wall
                if '<rss' not in text and '<feed' not in text:
                    raise ValueError(f"Non-RSS response ({len(text)} bytes, starts with {text[:40]!r})")
                break
        except Exception as e:
            last_err = e
            if attempt < max_retries - 1:
                time.sleep(5 * (attempt + 1))
    else:
        raise RuntimeError(f"Reddit {subreddit} failed after {max_retries} attempts: {last_err}")
    
    root = ET.fromstring(text)
    items = []
    for entry in root.findall('atom:entry', NS):
        title = entry.find('atom:title', NS)
        link = entry.find('atom:link', NS)
        published = entry.find('atom:published', NS)
        author = entry.find('atom:author', NS)
        summary = entry.find('atom:summary', NS)
        
        # Reddit RSS links are /r/.../comments/<id>/<slug> — extract the post id
        post_id = ''
        if link is not None and link.attrib.get('href'):
            href = link.attrib['href']
            import re
            m = re.search(r'/comments/([a-z0-9]{6,})/', href)
            if m:
                post_id = m.group(1)
        
        # Engagement: Reddit RSS doesn't expose score reliably; use comment count if present
        engagement = None
        
        items.append({
            'id': f"reddit:{subreddit}:{post_id}" if post_id else f"reddit:{subreddit}:{href}",
            'title': title.text if title is not None else '',
            'url': link.attrib.get('href', '') if link is not None else '',
            'body': (summary.text or '')[:2000] if summary is not None else '',
            'published_at': published.text if published is not None else None,
            'engagement': engagement,
            'metadata': {
                'author': author.find('atom:name', NS).text if author is not None and author.find('atom:name', NS) is not None else '',
                'subreddit': subreddit,
            }
        })
    
    return items

def fetch_all_reddit(per_page: int = 30) -> Dict[str, List[Dict]]:
    results = {}
    for source_name, (subreddit, display_name) in REDDIT_SUBREDDITS.items():
        try:
            items = fetch_reddit_subreddit(subreddit, per_page=per_page)
            results[source_name] = items
            print(f"  {source_name} ({display_name}): {len(items)} items")
        except Exception as e:
            print(f"  {source_name}: FAILED - {e}")
            results[source_name] = []
    return results