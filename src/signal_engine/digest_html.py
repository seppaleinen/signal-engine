"""
Digest markdown -> HTML rendering.

The digest markdown is constrained (see DIGEST_PROMPT in reading.py):

    # YYYY-MM-DD - one line headline

    ## Section heading
    - **Bold lead-in** - plain sentence, may contain `inline code`. [source](https://url)
    - one-liner with a link [text](https://url)

This module converts that structure into a standalone HTML document.
Everything text is escaped with html.escape; only structural tags and
sanitized http/https hrefs are emitted unescaped.
"""

import html
import re
from pathlib import Path
from typing import List

# Inline markdown pieces, applied to already-escaped text.
_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_CODE_RE = re.compile(r"`([^`]+)`")
_IMG_RE = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)\)")

_STYLE = (
    "body { font-family: -apple-system, BlinkMacSystemFont, \"Segoe UI\", Roboto, \"Helvetica Neue\", Arial, sans-serif;"
    "       max-width: 72ch; margin: 2rem auto; padding: 0 1rem; color: #1a1a1a;"
    "       line-height: 1.6; }"
    "h1 { font-size: 1.5rem; line-height: 1.3; border-bottom: 2px solid #e0e0e0;"
    "     padding-bottom: 0.5rem; }"
    "h2 { font-size: 1.2rem; margin-top: 1.8rem; color: #333; }"
    "ul { padding-left: 0; list-style: none; }"
    "li { margin-bottom: 1rem; }"
    "a { color: #0b5fff; text-decoration: none; }"
    "a:hover { text-decoration: underline; }"
    "code { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;"
    "       font-size: 0.9em; background: #f2f2f2; padding: 0.1em 0.3em;"
    "       border-radius: 3px; }"
    ""
    "/* Card layout for digest items */"
    ".digest-item { display: grid; grid-template-columns: 1fr; gap: 1rem; padding: 1rem; background: #fafafa; border-radius: 8px; border: 1px solid #eee; transition: box-shadow 0.2s, border-color 0.2s; }"
    ".digest-item:hover { box-shadow: 0 4px 12px rgba(0,0,0,0.08); border-color: #ddd; }"
    ".digest-item.has-thumbnail { grid-template-columns: 240px 1fr; }"
    "@media (max-width: 600px) { .digest-item.has-thumbnail { grid-template-columns: 1fr; } }"
    ""
    ".item-thumbnail { width: 100%; height: 135px; object-fit: cover; border-radius: 6px; background: #f0f0f0; }"
    ".item-content { display: flex; flex-direction: column; justify-content: center; min-width: 0; }"
    ".item-header { display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.4rem; flex-wrap: wrap; }"
    ".source-badge { display: inline-block; font-size: 0.7rem; font-weight: 600; padding: 0.15rem 0.5rem; border-radius: 999px; text-transform: uppercase; letter-spacing: 0.03em; color: #fff; }"
    ".source-youtube { background: #ff0000; }"
    ".source-reddit { background: #ff4500; }"
    ".source-github { background: #24292e; }"
    ".item-title { font-weight: 600; font-size: 1rem; line-height: 1.3; margin: 0; }"
    ".item-body { color: #444; font-size: 0.95rem; line-height: 1.5; margin: 0; }"
    ".item-links { display: flex; gap: 0.75rem; margin-top: 0.5rem; font-size: 0.85rem; }"
    ".item-links a { color: #0b5fff; }"
    ""
    "/* Also worth a look -- simpler list items */"
    ".also-list { list-style: none; padding: 0; }"
    ".also-list li { padding: 0.5rem 0; border-bottom: 1px solid #f0f0f0; }"
    ".also-list li:last-child { border-bottom: none; }"
)

_HTML_TEMPLATE = (
    "<!DOCTYPE html>"
    "<html lang=\"en\">"
    "<head>"
    "<meta charset=\"utf-8\">"
    "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
    "<title>{title}</title>"
    "<style>"
    "{style}"
    "</style>"
    "</head>"
    "<body>"
    "{body}"
    "</body>"
    "</html>"
)


def _render_text(text: str) -> str:
    """Escape text, then apply bold/code inline markup."""
    out = html.escape(text, quote=False)
    # Bold: **text**
    out = _BOLD_RE.sub(r"<strong>\1</strong>", out)
    # Inline code: `code`
    out = _CODE_RE.sub(r"<code>\1</code>", out)
    return out


def _render_inline(text: str) -> str:
    """Escape text, then apply links/bold/code inline markup.

    Links are matched on the raw text so their URL is only escaped once.
    """
    out: List[str] = []
    pos = 0
    for m in _LINK_RE.finditer(text):
        out.append(_render_text(text[pos:m.start()]))
        label = m.group(1)
        url = m.group(2)
        if re.match(r"^https?://", url, re.IGNORECASE):
            out.append(f'<a href="{html.escape(url, quote=True)}">{_render_text(label)}</a>')
        else:
            # Non-http(s) URL: emit the raw markdown text as plain text,
            # never as an href.
            out.append(_render_text(m.group(0)))
        pos = m.end()
    out.append(_render_text(text[pos:]))
    return "".join(out)


def _render_inline_with_img(text: str) -> str:
    """Like _render_inline but also handles image markdown ![alt](url)."""
    # First handle images
    out: List[str] = []
    pos = 0
    for m in _IMG_RE.finditer(text):
        out.append(_render_inline(text[pos:m.start()]))
        alt = m.group(1)
        url = m.group(2)
        if re.match(r"^https?://", url, re.IGNORECASE):
            out.append(f'<img src="{html.escape(url, quote=True)}" alt="{html.escape(alt)}" loading="lazy" class="inline-img">')
        else:
            out.append(_render_text(m.group(0)))
        pos = m.end()
    out.append(_render_inline(text[pos:]))
    return "".join(out)


def _extract_headline(markdown: str) -> str:
    """Headline from the first '# ' line, or the date, or a fallback."""
    for line in markdown.splitlines():
        line = line.strip()
        if line.startswith("# "):
            # Strip leading date prefix: "2026-10-16 - headline" -> "headline"
            text = line[2:].strip()
            m = re.match(r"^\d{4}-\d{2}-\d{2}\s*-\s*(.*)$", text)
            if m and m.group(1).strip():
                return m.group(1).strip()
            return text
    return "Signal Engine digest"


def _detect_source(source_text: str, url: str) -> str:
    """Detect source type from text or URL for badge."""
    text = (source_text + " " + url).lower()
    if "youtube.com" in text or "youtu.be" in text:
        return "youtube"
    if "reddit.com" in text:
        return "reddit"
    if "github.com" in text:
        return "github"
    return "generic"


def _parse_item_line(line: str) -> dict | None:
    """Parse a bullet line into structured parts: thumbnail, bold_lead, body, links."""
    content = line[2:].strip()  # Remove "- "
    if not content:
        return None

    # Extract thumbnail if present at start
    thumbnail_url = None
    img_match = _IMG_RE.match(content)
    if img_match:
        url = img_match.group(2)
        if re.match(r"^https?://", url, re.IGNORECASE):
            thumbnail_url = url
        # Remove the image markdown from content
        content = content[img_match.end():].lstrip()

    # Extract bold lead-in **text**
    bold_text = ""
    bold_match = _BOLD_RE.search(content)
    if bold_match:
        bold_text = bold_match.group(1)
        # Remove the bold markup for body parsing
        content = content[:bold_match.start()] + content[bold_match.end():]

    # Now parse links from the remaining content
    # Find all links
    links = []
    for m in _LINK_RE.finditer(content):
        label = m.group(1)
        url = m.group(2)
        if re.match(r"^https?://", url, re.IGNORECASE):
            links.append({"label": label, "url": url})

    # Body is content with links/bold/code rendered
    body_html = _render_inline_with_img(content).strip()

    return {
        "thumbnail": thumbnail_url,
        "bold": bold_text,
        "body": body_html,
        "links": links,
    }


def render_digest_html(markdown: str) -> str:
    """Render a digest markdown string as a full standalone HTML document."""
    parts: List[str] = []
    in_also_section = False
    seen_h1 = False

    for raw in markdown.splitlines():
        line = raw.rstrip()
        stripped = line.strip()

        if not stripped:
            continue

        # Headings
        if stripped.startswith("## "):
            section_name = stripped[3:].strip().lower()
            in_also_section = "also" in section_name
            parts.append(f"<h2>{_render_inline(stripped[3:])}</h2>")
            if in_also_section:
                parts.append('<ul class="also-list">')
            continue
        if stripped.startswith("# ") and not seen_h1:
            parts.append(f"<h1>{_render_inline(stripped[2:])}</h1>")
            seen_h1 = True
            continue

        # Bullets
        if stripped.startswith("- "):
            parsed = _parse_item_line(stripped)
            if not parsed:
                continue

            if in_also_section:
                # Simple list item for "Also worth a look"
                link_html = ""
                if parsed["links"]:
                    link_html = " -- " + " ".join(
                        f'<a href="{html.escape(l["url"])}">{_render_text(l["label"])}</a>'
                        for l in parsed["links"]
                    )
                bold_html = f"<strong>{_render_text(parsed['bold'])}</strong> " if parsed["bold"] else ""
                parts.append(f"<li>{bold_html}{parsed['body']}{link_html}</li>")
            else:
                # Card layout for Updates section
                source = "generic"
                if parsed["links"]:
                    source = _detect_source(parsed["links"][0]["label"], parsed["links"][0]["url"])

                badge_html = f'<span class="source-badge source-{source}">{source}</span>'
                thumb_html = ""
                has_thumb_class = ""
                if parsed["thumbnail"]:
                    thumb_html = f'<img src="{html.escape(parsed["thumbnail"])}" alt="" loading="lazy" class="item-thumbnail">'
                    has_thumb_class = " has-thumbnail"

                bold_html = f'<h3 class="item-title">{_render_text(parsed["bold"])}</h3>' if parsed["bold"] else ""
                links_html = ""
                if parsed["links"]:
                    links_html = '<div class="item-links">' + " ".join(
                        f'<a href="{html.escape(l["url"])}">{_render_text(l["label"])}</a>'
                        for l in parsed["links"]
                    ) + "</div>"

                card = (
                    f'<li class="digest-item{has_thumb_class}">'
                    f'{thumb_html}'
                    f'<div class="item-content">'
                    f'<div class="item-header">{badge_html}</div>'
                    f'{bold_html}'
                    f'<p class="item-body">{parsed["body"]}</p>'
                    f'{links_html}'
                    f'</div>'
                    f'</li>'
                )
                parts.append(card)
            continue

        # Unknown line: emit as an escaped paragraph (tolerate drift).
        parts.append(f"<p>{_render_inline(stripped)}</p>")

    if in_also_section:
        parts.append("</ul>")

    body = "\n".join(parts)
    title = _extract_headline(markdown)
    return _HTML_TEMPLATE.format(title=html.escape(title), style=_STYLE, body=body)


def digest_html_for_file(md_path: Path) -> str:
    """Render an existing digest .md file as a standalone HTML document."""
    md_path = Path(md_path)
    if not md_path.is_file():
        raise FileNotFoundError(md_path)
    return render_digest_html(md_path.read_text(encoding="utf-8"))