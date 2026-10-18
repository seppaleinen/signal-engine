import json
import subprocess
from typing import Dict, List

from signal_engine.config import get_github_sources


def fetch_github_releases(owner: str, repo: str, per_page: int = 50) -> List[Dict]:
    url = f"https://api.github.com/repos/{owner}/{repo}/releases"
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "signal-engine"}
    
    # Make HTTP request via curl subprocess
    curl_headers = []
    for key, value in headers.items():
        curl_headers.extend(["-H", f"{key}: {value}"])

    # Build URL with query parameters
    full_url = f"{url}?per_page={per_page}"

    result = subprocess.run(
        ["curl", "-k", "-s", "--max-time", "30"] + curl_headers + [full_url],
        capture_output=True,
        text=True,
        timeout=35
    )

    if result.returncode != 0:
        raise Exception(f"Curl failed: {result.stderr}")

    releases = json.loads(result.stdout)
    
    items = []
    for rel in releases:
        item_id = f"github:{owner}/{repo}:{rel['tag_name']}"
        body = rel.get('body') or ''
        items.append({
            'id': item_id,
            'title': rel['name'] or rel['tag_name'],
            'url': rel['html_url'],
            'body': body[:2000],
            'published_at': rel.get('published_at'),
            'engagement': len(rel.get('assets', [])),
            'metadata': {
                'draft': rel.get('draft', False),
                'prerelease': rel.get('prerelease', False),
                'tag_name': rel['tag_name'],
                'owner': owner,
                'repo': repo,
            }
        })
    
    return items

def fetch_all_sources(per_page: int = 50, skip_drafts: bool = True) -> Dict[str, List[Dict]]:
    """Fetch every registered GitHub source. Returns {source_name: [items]}."""
    results = {}
    for source_name, cfg in get_github_sources().items():
        owner = cfg["owner"]
        repo = cfg["repo"]
        display_name = cfg.get("display_name", source_name)
        try:
            items = fetch_github_releases(owner, repo, per_page=per_page)
            if skip_drafts:
                items = [i for i in items if not i['metadata'].get('draft')]
            results[source_name] = items
            print(f"  {source_name} ({display_name}): {len(items)} items")
        except Exception as e:
            print(f"  {source_name}: FAILED - {e}")
            results[source_name] = []
    return results