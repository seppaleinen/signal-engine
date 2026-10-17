"""
Web viewer for digest files.

Serves an index of all digests and per-digest pages, using only the
standard library (http.server.ThreadingHTTPServer + BaseHTTPRequestHandler).
"""

import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import List, Tuple

from signal_engine.digest_html import digest_html_for_file

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_MD_RE = re.compile(r"^\d{4}-\d{2}-\d{2}\.md$")
_HEADLINE_RE = re.compile(r"^#\s+\d{4}-\d{2}-\d{2}\s*-\s*(.*)$")

_INDEX_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Digests</title>
<style>
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
       max-width: 72ch; margin: 2rem auto; padding: 0 1rem; color: #1a1a1a;
       line-height: 1.6; }
h1 { font-size: 1.5rem; border-bottom: 2px solid #e0e0e0; padding-bottom: 0.5rem; }
ul { padding-left: 1.3rem; }
li { margin-bottom: 0.5rem; }
a { color: #0b5fff; text-decoration: none; }
a:hover { text-decoration: underline; }
.muted { color: #888; font-size: 0.9rem; }
</style>
</head>
<body>
<h1>Digests</h1>
<ul>
{links}
</ul>
<p class="muted">{count} digest(s)</p>
</body>
</html>
"""


def _scan_digests(digest_dir: Path) -> List[Tuple[str, str]]:
    """Return [(date, headline), ...] for every YYYY-MM-DD.md, newest first."""
    if not digest_dir.is_dir():
        return []
    out: List[Tuple[str, str]] = []
    for entry in digest_dir.iterdir():
        if not entry.is_file() or not _MD_RE.match(entry.name):
            continue
        date = entry.name[:10]
        headline = _extract_headline(entry)
        out.append((date, headline))
    out.sort(key=lambda x: x[0], reverse=True)
    return out


def _extract_headline(md_path: Path) -> str:
    """Headline from the first '# ' line, or a fallback."""
    try:
        with md_path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line.startswith("# "):
                    m = _HEADLINE_RE.match(line)
                    if m and m.group(1).strip():
                        return m.group(1).strip()
                    return line[2:].strip()
    except OSError:
        pass
    return "(no headline)"


def _build_index(digest_dir: Path) -> str:
    digests = _scan_digests(digest_dir)
    if not digests:
        links = '<li class="muted">No digests yet.</li>'
    else:
        links = "\n".join(
            f'  <li><a href="/{date}/">{date}</a> — {headline}</li>'
            for date, headline in digests
        )
    return _INDEX_HTML_TEMPLATE.replace("{links}", links).replace("{count}", str(len(digests)))


class _DigestHandler(BaseHTTPRequestHandler):
    digest_dir: Path = Path("digests")

    def log_message(self, fmt, *args):
        print(f"[viewer] {self.address_string()} - {fmt % args}", file=sys.stderr)

    def _send(self, status: int, body: bytes, content_type: str = "text/html; charset=utf-8"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _serve_digest(self, date: str):
        """Serve a digest by date. date is already regex-validated."""
        digest_root = self.digest_dir.resolve()
        candidates: List[Path] = []
        html_path = (self.digest_dir / f"{date}.html").resolve()
        md_path = (self.digest_dir / f"{date}.md").resolve()
        for candidate in (html_path, md_path):
            try:
                candidate.relative_to(digest_root)
            except ValueError:
                self._send(404, b"Not found")
                return
            candidates.append(candidate)

        # Prefer the pre-rendered HTML.
        if candidates[0].is_file():
            try:
                self._send(200, candidates[0].read_bytes())
                return
            except OSError:
                pass
        # Fall back to on-the-fly render from the markdown.
        if candidates[1].is_file():
            try:
                html_text = digest_html_for_file(candidates[1])
            except OSError:
                self._send(404, b"Not found")
                return
            self._send(200, html_text.encode("utf-8"))
            return
        self._send(404, b"Not found")

    def do_GET(self):
        path = self.path.split("?", 1)[0].split("#", 1)[0]
        path = path.rstrip("/")
        if path == "" or path == "/":
            self._send(200, _build_index(self.digest_dir).encode("utf-8"))
            return
        # /YYYY-MM-DD or /YYYY-MM-DD.html
        if path.startswith("/"):
            seg = path[1:]
            if seg.endswith(".html"):
                date = seg[:-5]
            else:
                date = seg
            if not _DATE_RE.match(date):
                self._send(400, b"Bad request")
                return
            self._serve_digest(date)
            return
        self._send(404, b"Not found")

    def do_HEAD(self):
        # Minimal: reuse GET logic for the path check.
        self.do_GET()


def run_viewer(digest_dir: str = "digests", host: str = "0.0.0.0", port: int = 8000) -> int:
    """Start the digest web viewer. Returns 0 on clean shutdown."""
    _DigestHandler.digest_dir = Path(digest_dir).resolve()
    server = ThreadingHTTPServer((host, port), _DigestHandler)
    print(f"Serving digests from {_DigestHandler.digest_dir} on http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down viewer.")
    finally:
        server.server_close()
    return 0