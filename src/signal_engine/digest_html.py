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

_STYLE = """\
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
       max-width: 72ch; margin: 2rem auto; padding: 0 1rem; color: #1a1a1a;
       line-height: 1.6; }
h1 { font-size: 1.5rem; line-height: 1.3; border-bottom: 2px solid #e0e0e0;
     padding-bottom: 0.5rem; }
h2 { font-size: 1.2rem; margin-top: 1.8rem; color: #333; }
ul { padding-left: 1.3rem; }
li { margin-bottom: 0.7rem; }
a { color: #0b5fff; text-decoration: none; }
a:hover { text-decoration: underline; }
code { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
       font-size: 0.9em; background: #f2f2f2; padding: 0.1em 0.3em;
       border-radius: 3px; }
"""

_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
{style}
</style>
</head>
<body>
{body}
</body>
</html>
"""


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


def render_digest_html(markdown: str) -> str:
    """Render a digest markdown string as a full standalone HTML document."""
    parts: List[str] = []
    in_list = False
    seen_h1 = False

    def close_list() -> None:
        nonlocal in_list
        if in_list:
            parts.append("</ul>")
            in_list = False

    for raw in markdown.splitlines():
        line = raw.rstrip()
        stripped = line.strip()

        if not stripped:
            close_list()
            continue

        # Headings
        if stripped.startswith("## "):
            close_list()
            parts.append(f"<h2>{_render_inline(stripped[3:])}</h2>")
            continue
        if stripped.startswith("# ") and not seen_h1:
            # First h1: page heading (title + headline)
            parts.append(f"<h1>{_render_inline(stripped[2:])}</h1>")
            seen_h1 = True
            continue

        # Bullets
        if stripped.startswith("- "):
            if not in_list:
                parts.append("<ul>")
                in_list = True
            parts.append(f"<li>{_render_inline(stripped[2:])}</li>")
            continue

        # Unknown line: emit as an escaped paragraph (tolerate drift).
        close_list()
        parts.append(f"<p>{_render_inline(stripped)}</p>")

    close_list()

    body = "\n".join(parts)
    title = _extract_headline(markdown)
    return _HTML_TEMPLATE.format(title=html.escape(title), style=_STYLE, body=body)


def digest_html_for_file(md_path: Path) -> str:
    """Render an existing digest .md file as a standalone HTML document."""
    md_path = Path(md_path)
    if not md_path.is_file():
        raise FileNotFoundError(md_path)
    return render_digest_html(md_path.read_text(encoding="utf-8"))
