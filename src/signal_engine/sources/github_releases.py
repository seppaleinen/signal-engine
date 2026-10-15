import httpx
from typing import List, Dict
from datetime import datetime

def fetch_github_releases(owner: str, repo: str, per_page: int = 30) -> List[Dict]:
    url = f"https://api.github.com/repos/{owner}/{repo}/releases"
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "signal-engine"}
    
    with httpx.Client(timeout=30.0) as client:
        resp = client.get(url, params={"per_page": per_page}, headers=headers)
        resp.raise_for_status()
        releases = resp.json()
    
    items = []
    for rel in releases:
        # Stable id: github:owner/repo:tag
        item_id = f"github:{owner}/{repo}:{rel['tag_name']}"
        
        # Body: take first 2000 chars of body (strip markdown for now)
        body = rel.get('body') or ''
        body_short = body[:2000]
        
        # Published at
        published = rel.get('published_at')
        
        # Engagement: downloads or reactions? Use stars of repo for engagement weighting
        # For now, use the release asset count as a proxy
        asset_count = len(rel.get('assets', []))
        
        items.append({
            'id': item_id,
            'title': f"{rel['name'] or rel['tag_name']}",
            'url': rel['html_url'],
            'body': body_short,
            'published_at': published,
            'engagement': asset_count,
            'metadata': {
                'draft': rel.get('draft', False),
                'prerelease': rel.get('prerelease', False),
                'tag_name': rel['tag_name']
            }
        })
    
    return items

def main():
    # Example run for llama.cpp
    items = fetch_github_releases("ggerganov", "llama.cpp", per_page=20)
    print(f"Fetched {len(items)} releases")
    for item in items[:3]:
        print(f" - {item['title']} | {item['id']}")
    return items