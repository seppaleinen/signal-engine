import xml.etree.ElementTree as ET
from typing import Dict, List

import httpx

# Verified channel IDs (R2.2). RSS is free — no API key needed.
YOUTUBE_CHANNELS = {
    "betterstack": ("UCkVfrGwV-iG9bSsgCbrNPxQ", "Better Stack"),
    "aiDotEngineer": ("UCLKPca3kwwd-B59HNr-_lvA", "AI Engineer"),
    "fireship": ("UCsBjURrPoezykLs9EqgamOA", "Fireship"),
}

NS = {
    'atom': 'http://www.w3.org/2005/Atom',
    'media': 'http://search.yahoo.com/mrss/',
    'yt': 'http://www.youtube.com/xml/schemas/2015',
}

def fetch_youtube_channel(channel_id: str, per_page: int = 50) -> List[Dict]:
    url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}&max_results={min(per_page, 50)}"
    headers = {"User-Agent": "signal-engine/1.0"}
    
    with httpx.Client(timeout=30.0) as client:
        resp = client.get(url, headers=headers)
        resp.raise_for_status()
    
    root = ET.fromstring(resp.text)
    items = []
    for entry in root.findall('atom:entry', NS):
        video_id = entry.find('atom:yt:videoId', NS)
        title = entry.find('atom:title', NS)
        entry.find('atom:link', NS)
        published = entry.find('atom:published', NS)
        author = entry.find('atom:author', NS)
        media_group = entry.find('media:group', NS)
        
        views = None
        if media_group is not None:
            v = media_group.find('media:statistics', NS)
            if v is not None and 'views' in v.attrib:
                views = int(v.attrib['views'])
        
        vid = video_id.text if video_id is not None else ''
        items.append({
            'id': f"youtube:{vid}",
            'title': title.text if title is not None else '',
            'url': f"https://www.youtube.com/watch?v={vid}",
            'body': '',
            'published_at': published.text if published is not None else None,
            'engagement': views,
            'metadata': {
                'author': author.find('atom:name', NS).text if author is not None and author.find('atom:name', NS) is not None else '',
                'channel_id': channel_id,
            }
        })
    
    return items

def fetch_all_youtube(per_page: int = 50) -> Dict[str, List[Dict]]:
    results = {}
    for source_name, (channel_id, display_name) in YOUTUBE_CHANNELS.items():
        try:
            items = fetch_youtube_channel(channel_id, per_page=per_page)
            results[source_name] = items
            print(f"  {source_name} ({display_name}): {len(items)} items")
        except Exception as e:
            print(f"  {source_name}: FAILED - {e}")
            results[source_name] = []
    return results