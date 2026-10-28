import subprocess
import xml.etree.ElementTree as ET
from typing import Dict, List

from signal_engine.config import get_youtube_channels

NS = {
    'atom': 'http://www.w3.org/2005/Atom',
    'media': 'http://search.yahoo.com/mrss/',
    'yt': 'http://www.youtube.com/xml/schemas/2015',
}

def fetch_youtube_channel(channel_id: str, per_page: int = 50) -> List[Dict]:
    url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}&max_results={min(per_page, 50)}"
    headers = {"User-Agent": "signal-engine/1.0"}
    
    # Make HTTP request via curl subprocess
    curl_headers = []
    for key, value in headers.items():
        curl_headers.extend(["-H", f"{key}: {value}"])

    result = subprocess.run(
        ["curl", "-k", "-s", "--max-time", "30"] + curl_headers + [url],
        capture_output=True,
        text=True,
        timeout=35
    )

    if result.returncode != 0:
        raise Exception(f"Curl failed: {result.stderr}")

    root = ET.fromstring(result.stdout)
    items = []
    for entry in root.findall('atom:entry', NS):
        video_id = entry.find('yt:videoId', NS)
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

        # Extract thumbnail from media:group/media:thumbnail
        thumbnail_url = None
        if media_group is not None:
            thumb = media_group.find('media:thumbnail', NS)
            if thumb is not None and 'url' in thumb.attrib:
                thumbnail_url = thumb.attrib['url']

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
                'thumbnail': thumbnail_url,
            }
        })
    
    return items

def fetch_all_youtube(per_page: int = 50) -> Dict[str, List[Dict]]:
    results = {}
    for source_name, cfg in get_youtube_channels().items():
        channel_id = cfg["channel_id"]
        display_name = cfg["display_name"]
        try:
            items = fetch_youtube_channel(channel_id, per_page=per_page)
            results[source_name] = items
            print(f"  {source_name} ({display_name}): {len(items)} items")
        except Exception as e:
            print(f"  {source_name}: FAILED - {e}")
            results[source_name] = []
    return results