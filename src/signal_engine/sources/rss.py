"""Generic RSS/Atom source — fetches and parses any RSS or Atom feed.

Supports both RSS 2.0 and Atom 1.0 formats. Used for newsletters that don't
have a native API (e.g. TLDR via Kill-the-Newsletter).
"""

import subprocess
import xml.etree.ElementTree as ET
from typing import Dict, List

from signal_engine.config import get_rss_sources

NS = {
    'atom': 'http://www.w3.org/2005/Atom',
    'media': 'http://search.yahoo.com/mrss/',
    'dc': 'http://purl.org/dc/elements/1.1/',
    'content': 'http://purl.org/rss/1.0/modules/content/',
}


def _text(elem, tag: str, ns: dict) -> str:
    """Get text from a child element, or empty string if missing."""
    child = elem.find(tag, ns)
    return child.text if child is not None and child.text else ''


def _get_link(entry: ET.Element, ns: dict) -> str:
    """Get the primary link URL from an RSS/Atom entry.

    Atom: <link rel="alternate" href="..."/> or just <link href="..."/>
    RSS:  <link>http://...</link>
    """
    # Atom: try alternate link first, then any link
    link = entry.find('atom:link[@rel="alternate"]', ns)
    if link is None:
        link = entry.find('atom:link', ns)
    if link is not None and 'href' in link.attrib:
        return link.attrib['href']
    # RSS: <link>text</link>
    link = entry.find('link')
    if link is not None and link.text:
        return link.text.strip()
    return ''


def _get_published(entry: ET.Element, ns: dict) -> str | None:
    """Get publication date from an RSS/Atom entry."""
    # Atom: <published> or <updated>
    for tag in ('atom:published', 'atom:updated'):
        val = _text(entry, tag, ns)
        if val:
            return val
    # RSS: <pubDate> or <dc:date>
    for tag in ('pubDate', 'dc:date'):
        val = _text(entry, tag, ns)
        if val:
            return val
    return None


def _get_description(entry: ET.Element, ns: dict) -> str:
    """Get description/body text from an RSS/Atom entry."""
    # Atom: <summary> or <content>
    for tag in ('atom:summary', 'atom:content'):
        val = _text(entry, tag, ns)
        if val:
            return val
    # RSS: <description> or <content:encoded>
    for tag in ('description', 'content:encoded'):
        val = _text(entry, tag, ns)
        if val:
            return val
    return ''


def _get_thumbnail(entry: ET.Element, ns: dict) -> str | None:
    """Get thumbnail URL from an RSS/Atom entry (media:thumbnail)."""
    mg = entry.find('media:group', ns)
    if mg is not None:
        thumb = mg.find('media:thumbnail', ns)
        if thumb is not None and 'url' in thumb.attrib:
            return thumb.attrib['url']
    # RSS media:thumbnail directly on entry
    thumb = entry.find('media:thumbnail', ns)
    if thumb is not None and 'url' in thumb.attrib:
        return thumb.attrib['url']
    return None


def fetch_rss_feed(feed_url: str, per_page: int = 50) -> List[Dict]:
    """Fetch and parse a generic RSS or Atom feed.

    Handles both RSS 2.0 and Atom 1.0 formats transparently.
    """
    headers = {"User-Agent": "signal-engine/1.0"}

    curl_headers = []
    for key, value in headers.items():
        curl_headers.extend(["-H", f"{key}: {value}"])

    result = subprocess.run(
        ["curl", "-k", "-s", "--max-time", "30"] + curl_headers + [feed_url],
        capture_output=True,
        text=True,
        timeout=35
    )

    if result.returncode != 0:
        raise Exception(f"Curl failed: {result.stderr}")

    text = result.stdout
    if not text or ('<rss' not in text and '<feed' not in text):
        raise ValueError(f"Non-RSS response ({len(text)} bytes)")

    root = ET.fromstring(text)

    # Detect format: Atom has <feed> root, RSS has <rss> root
    is_atom = root.tag.endswith('feed')
    is_rss = root.tag.endswith('rss') or root.tag.endswith('rss')

    if is_atom:
        entries = root.findall('atom:entry', NS)
    elif is_rss:
        # RSS root may have a channel child with item elements
        channel = root.find('channel')
        if channel is not None:
            entries = channel.findall('item')
        else:
            entries = root.findall('item')
    else:
        # Unknown format — try both
        entries = root.findall('atom:entry', NS)
        if not entries:
            channel = root.find('channel')
            entries = channel.findall('item') if channel is not None else []

    items = []
    for entry in entries[:per_page]:
        title = _text(entry, 'title', NS)
        if not title:
            continue

        url = _get_link(entry, NS)
        published = _get_published(entry, NS)
        body = _get_description(entry, NS)
        thumbnail = _get_thumbnail(entry, NS)

        # Generate a stable id from URL or title+published
        import re
        item_id = f"rss:{re.sub(r'[^a-zA-Z0-9]', '', url or title)[:60]}"

        items.append({
            'id': item_id,
            'title': title,
            'url': url,
            'body': body[:2000],
            'published_at': published,
            'engagement': None,
            'metadata': {
                'thumbnail': thumbnail,
                'format': 'atom' if is_atom else 'rss',
            }
        })

    return items


def fetch_all_rss(per_page: int = 50) -> Dict[str, List[Dict]]:
    """Fetch every registered RSS source. Returns {source_name: [items]}."""
    results = {}
    for source_name, cfg in get_rss_sources().items():
        feed_url = cfg["feed_url"]
        display_name = cfg["display_name"]
        try:
            items = fetch_rss_feed(feed_url, per_page=per_page)
            results[source_name] = items
            print(f"  {source_name} ({display_name}): {len(items)} items")
        except Exception as e:
            print(f"  {source_name}: FAILED - {e}")
            results[source_name] = []
    return results