from typing import Dict, List

import httpx

# Source registry: source_name -> (owner, repo)
# Populated from PROFILE.md + GitHub API verification (all return 200).
GITHUB_SOURCES = {
    "opencode-releases": ("anomalyco", "opencode"),
    "llama-swap-releases": ("mostlygeek", "llama-swap"),
    "hindsight-releases": ("vectorize-io", "hindsight"),
    "litellm-releases": ("BerriAI", "litellm"),
    "lmstudio-releases": ("lmstudio-ai", "lms"),
    "lmstudio-js-releases": ("lmstudio-ai", "lmstudio-js"),
    "lmstudio-python-releases": ("lmstudio-ai", "lmstudio-python"),
    "git-releases": ("git", "git"),
}

def fetch_github_releases(owner: str, repo: str, per_page: int = 50) -> List[Dict]:
    url = f"https://api.github.com/repos/{owner}/{repo}/releases"
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "signal-engine"}
    
    with httpx.Client(timeout=30.0) as client:
        resp = client.get(url, params={"per_page": per_page}, headers=headers)
        resp.raise_for_status()
        releases = resp.json()
    
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
    for source_name, (owner, repo) in GITHUB_SOURCES.items():
        try:
            items = fetch_github_releases(owner, repo, per_page=per_page)
            if skip_drafts:
                items = [i for i in items if not i['metadata'].get('draft')]
            results[source_name] = items
            print(f"  {source_name}: {len(items)} items")
        except Exception as e:
            print(f"  {source_name}: FAILED - {e}")
            results[source_name] = []
    return results