"""
Web viewer for digest files.

Serves an index of all digests and per-digest pages, using only the
standard library (http.server.ThreadingHTTPServer + BaseHTTPRequestHandler).
"""

import json
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import List, Tuple

from signal_engine.config import (
    ConfigError,
    _validate_config,
    get_config_path,
    load_config,
    save_config,
)
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

# ADMIN UI TEMPLATE — sources management page
_ADMIN_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Signal Engine — Source Admin</title>
<style>
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
       max-width: 900px; margin: 2rem auto; padding: 0 1rem; color: #1a1a1a; line-height: 1.6; }
h1 { font-size: 1.5rem; border-bottom: 2px solid #e0e0e0; padding-bottom: 0.5rem; }
h2 { font-size: 1.2rem; margin-top: 2rem; border-bottom: 1px solid #e0e0e0; padding-bottom: 0.3rem; }
ul { padding-left: 1.3rem; }
li { margin-bottom: 0.5rem; }
a { color: #0b5fff; text-decoration: none; }
a:hover { text-decoration: underline; }
.muted { color: #888; font-size: 0.9rem; }
button { background: #0b5fff; color: white; border: none; padding: 0.4rem 0.8rem; border-radius: 4px; cursor: pointer; font-size: 0.9rem; }
button:hover { background: #004de6; }
button.secondary { background: #f0f0f0; color: #333; }
button.secondary:hover { background: #e0e0e0; }
button.danger { background: #e03; }
button.danger:hover { background: #c00; }
input, select { padding: 0.3rem 0.5rem; border: 1px solid #ccc; border-radius: 4px; font-size: 0.9rem; margin-right: 0.5rem; }
input[type="checkbox"] { margin-right: 0.3rem; }
.form-group { margin-bottom: 0.8rem; }
label { display: block; margin-bottom: 0.2rem; font-weight: 500; }
.source-item { display: flex; align-items: center; gap: 0.5rem; padding: 0.5rem; border: 1px solid #eee; border-radius: 4px; margin-bottom: 0.5rem; }
.source-item:hover { background: #fafafa; }
.source-info { flex: 1; }
.source-name { font-weight: 600; }
.source-meta { color: #666; font-size: 0.85rem; }
.source-actions { display: flex; gap: 0.3rem; }
.section-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem; }
.modal { position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.5); display: flex; align-items: center; justify-content: center; z-index: 100; }
.modal.hidden { display: none; }
.modal-content { background: white; padding: 1.5rem; border-radius: 8px; width: 100%; max-width: 500px; max-height: 90vh; overflow-y: auto; }
.toast { position: fixed; bottom: 1rem; right: 1rem; padding: 0.8rem 1rem; border-radius: 4px; color: white; font-weight: 500; z-index: 200; }
.toast.success { background: #28a745; }
.toast.error { background: #dc3545; }
.toast.hidden { display: none; }
</style>
</head>
<body>
<h1>Source Admin</h1>
<p class="muted">Manage YouTube channels, Reddit subreddits, and GitHub repos. Changes persist to <code>config/sources.yaml</code>.</p>

<div id="toast" class="toast hidden"></div>

<section id="youtube">
  <div class="section-header">
    <h2>YouTube Channels</h2>
    <button onclick="openModal('youtube')">Add Channel</button>
  </div>
  <ul id="youtube-list"></ul>
</section>

<section id="reddit">
  <div class="section-header">
    <h2>Reddit Subreddits</h2>
    <button onclick="openModal('reddit')">Add Subreddit</button>
  </div>
  <ul id="reddit-list"></ul>
</section>

<section id="github">
  <div class="section-header">
    <h2>GitHub Repos</h2>
    <button onclick="openModal('github')">Add Repo</button>
  </div>
  <ul id="github-list"></ul>
</section>

<div id="modal" class="modal hidden" role="dialog">
  <div class="modal-content">
    <h2 id="modal-title">Add Source</h2>
    <form id="modal-form">
      <input type="hidden" name="source_type" id="modal-type">
      <input type="hidden" name="source_name" id="modal-name">
      <div class="form-group">
        <label>Display Name <span class="muted">(used for source_name if not provided)</span></label>
        <input type="text" name="display_name" id="modal-display" required>
      </div>
      <div class="form-group" id="modal-youtube-fields" style="display:none;">
        <label>Channel ID</label>
        <input type="text" name="channel_id" id="modal-channel-id" required>
      </div>
      <div class="form-group" id="modal-reddit-fields" style="display:none;">
        <label>Subreddit (e.g. LocalLLM)</label>
        <input type="text" name="subreddit" id="modal-subreddit" required>
      </div>
      <div class="form-group" id="modal-github-fields" style="display:none;">
        <label>Owner</label>
        <input type="text" name="owner" id="modal-owner" required>
        <label>Repo</label>
        <input type="text" name="repo" id="modal-repo" required>
      </div>
      <div class="form-group">
        <label><input type="checkbox" name="enabled" id="modal-enabled" checked> Enabled</label>
      </div>
      <div style="display:flex; gap:0.5rem; justify-content:flex-end; margin-top:1rem;">
        <button type="button" class="secondary" onclick="closeModal()">Cancel</button>
        <button type="submit">Save</button>
      </div>
    </form>
  </div>
</div>

<script>
const API = '/admin/sources';

function showToast(msg, type='success') {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.className = 'toast ' + type;
  setTimeout(() => t.classList.add('hidden'), 3000);
}

async function fetchAPI(path, opts={}) {
  const res = await fetch(path, {
    headers: {'Content-Type': 'application/json', ...(opts.headers||{})},
    ...opts
  });
  const data = await res.json().catch(()=>({}));
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data;
}

function renderSources() {
  fetchAPI(API).then(cfg => {
    renderSection('youtube', cfg.youtube || {}, 'channel_id');
    renderSection('reddit', cfg.reddit || {}, 'subreddit');
    renderSection('github', cfg.github || {}, 'owner');
  }).catch(e => showToast('Failed to load sources: '+e, 'error'));
}

function renderSection(type, sources, keyField) {
  const list = document.getElementById(type+'-list');
  list.innerHTML = '';
  for (const [name, entry] of Object.entries(sources)) {
    const li = document.createElement('li');
    li.className = 'source-item';
    const meta = entry[keyField] || (entry.owner ? entry.owner+'/'+entry.repo : '');
    const display = entry.display_name || name;
    li.innerHTML = `
      <div class="source-info">
        <div class="source-name">${escapeHtml(display)} <span class="muted">(${name})</span></div>
        <div class="source-meta">${escapeHtml(meta)} · ${entry.enabled ? 'enabled' : '<span style="color:#e03">disabled</span>'}</div>
      </div>
      <div class="source-actions">
        <input type="checkbox" ${entry.enabled ? 'checked' : ''} onchange="toggleSource('${type}', '${name}', this.checked)">
        <button class="secondary" onclick="openModal('${type}', '${name}')">Edit</button>
        <button class="danger" onclick="deleteSource('${type}', '${name}')">Delete</button>
      </div>
    `;
    list.appendChild(li);
  }
}

function escapeHtml(str) {
  return String(str).replace(/[&<>"']/g, c => ({'&':'&','<':'<','>':'>','"':'"',"'":'''}[c]));
}

function openModal(type, name=null) {
  document.getElementById('modal-type').value = type;
  document.getElementById('modal-name').value = name || '';
  document.getElementById('modal-display').value = '';
  document.getElementById('modal-enabled').checked = true;
  document.getElementById('modal-channel-id').value = '';
  document.getElementById('modal-subreddit').value = '';
  document.getElementById('modal-owner').value = '';
  document.getElementById('modal-repo').value = '';
  document.querySelectorAll('[id^="modal-"][id$="-fields"]').forEach(el => el.style.display='none');
  document.getElementById('modal-'+type+'-fields').style.display='block';
  if (name) {
    document.getElementById('modal-title').textContent = 'Edit ' + type;
    document.getElementById('modal-display').value = name;
    // load existing
    fetchAPI(API).then(cfg => {
      const e = cfg[type][name];
      if (e) {
        document.getElementById('modal-display').value = e.display_name || name;
        document.getElementById('modal-enabled').checked = e.enabled;
        if (type==='youtube') document.getElementById('modal-channel-id').value = e.channel_id;
        if (type==='reddit') document.getElementById('modal-subreddit').value = e.subreddit;
        if (type==='github') { document.getElementById('modal-owner').value = e.owner; document.getElementById('modal-repo').value = e.repo; }
      }
    });
  } else {
    document.getElementById('modal-title').textContent = 'Add ' + type;
  }
  document.getElementById('modal').classList.remove('hidden');
}

function closeModal() {
  document.getElementById('modal').classList.add('hidden');
}

document.getElementById('modal-form').addEventListener('submit', async e => {
  e.preventDefault();
  const form = e.target;
  const type = form.source_type.value;
  const name = form.source_name.value;
  const data = {
    display_name: form.display_name.value,
    enabled: form.enabled.checked
  };
  if (type==='youtube') data.channel_id = form.channel_id.value;
  if (type==='reddit') data.subreddit = form.subreddit.value;
  if (type==='github') { data.owner = form.owner.value; data.repo = form.repo.value; }
  try {
    if (name) {
      await fetchAPI(API + '/' + type + '/' + name, {method:'PATCH', body:JSON.stringify(data)});
      showToast('Updated ' + type + '/' + name);
    } else {
      await fetchAPI(API + '/' + type, {method:'POST', body:JSON.stringify(data)});
      showToast('Added ' + type);
    }
    closeModal();
    renderSources();
  } catch (err) {
    showToast(err.message, 'error');
  }
});

async function toggleSource(type, name, enabled) {
  try {
    await fetchAPI(API + '/' + type + '/' + name, {method:'PATCH', body:JSON.stringify({enabled})});
    showToast((enabled?'Enabled':'Disabled') + ' ' + type + '/' + name);
    renderSources();
  } catch (err) {
    showToast(err.message, 'error');
    renderSources(); // revert UI
  }
}

async function deleteSource(type, name) {
  if (!confirm('Delete ' + type + '/' + name + '?')) return;
  try {
    await fetchAPI(API + '/' + type + '/' + name, {method:'DELETE'});
    showToast('Deleted ' + type + '/' + name);
    renderSources();
  } catch (err) {
    showToast(err.message, 'error');
  }
}

renderSources();
</script>
</body>
</html>"""


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
    config_path: Path = Path("config/sources.yaml")

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
        if path == "/admin":
            self._send(200, _ADMIN_HTML_TEMPLATE.encode("utf-8"))
            return
        if path == "/admin/sources":
            try:
                cfg = load_config()
                body = json.dumps(cfg).encode("utf-8")
                self._send(200, body, content_type="application/json")
            except ConfigError as e:
                self._send(400, json.dumps({"error": str(e)}).encode("utf-8"), content_type="application/json")
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

    def _json_send(self, status: int, obj: dict):
        body = json.dumps(obj).encode("utf-8")
        self._send(status, body, content_type="application/json")

    def _read_json_body(self):
        content_len = int(self.headers.get("Content-Length", "0"))
        if content_len <= 0:
            return None
        body_bytes = self.rfile.read(content_len)
        if not body_bytes:
            return None
        try:
            return json.loads(body_bytes)
        except json.JSONDecodeError:
            return "error"

    def do_POST(self):
        path = self.path.split("?", 1)[0].split("#", 1)[0].rstrip("/")
        parts = path.split("/")
        if len(parts) != 4 or parts[1] != "admin" or parts[2] != "sources":
            self.send_response(404)
            self.end_headers()
            return
        type_ = parts[3]
        if type_ not in {"youtube", "reddit", "github"}:
            self._json_send(400, {"error": "unknown source type"})
            return
        data = self._read_json_body()
        if data is None or data == "error":
            self._json_send(400, {"error": "invalid JSON body"})
            return
        source_name = data.get("source_name")
        if source_name:
            if not re.match(r"^[a-zA-Z0-9_-]+$", source_name):
                self._json_send(400, {"error": "invalid source_name"})
                return
        else:
            display_name = data.get("display_name")
            if not display_name:
                self._json_send(400, {"error": "display_name required to generate source_name"})
                return
            slug = re.sub(r"[^a-z0-9]+", "_", str(display_name).lower()).strip("_")
            source_name = slug
        cfg = load_config()
        section = cfg.get(type_, {})
        if source_name in section:
            self._json_send(409, {"error": f"source already exists: {source_name}"})
            return
        # Build entry with validation
        entry: dict = {}
        enabled = data.get("enabled", True)
        if not isinstance(enabled, bool):
            self._json_send(400, {"error": "enabled must be bool"})
            return
        if type_ == "youtube":
            channel_id = data.get("channel_id")
            display_name = data.get("display_name")
            if not isinstance(channel_id, str) or not channel_id.strip():
                self._json_send(400, {"error": "channel_id required"})
                return
            if not isinstance(display_name, str) or not display_name.strip():
                self._json_send(400, {"error": "display_name required"})
                return
            entry = {"channel_id": channel_id.strip(), "display_name": display_name.strip(), "enabled": enabled}
        elif type_ == "reddit":
            subreddit = data.get("subreddit")
            display_name = data.get("display_name")
            if not isinstance(subreddit, str) or not subreddit.strip():
                self._json_send(400, {"error": "subreddit required"})
                return
            if not isinstance(display_name, str) or not display_name.strip():
                self._json_send(400, {"error": "display_name required"})
                return
            entry = {"subreddit": subreddit.strip(), "display_name": display_name.strip(), "enabled": enabled}
        else:  # github
            owner = data.get("owner")
            repo = data.get("repo")
            if not isinstance(owner, str) or not owner.strip():
                self._json_send(400, {"error": "owner required"})
                return
            if not isinstance(repo, str) or not repo.strip():
                self._json_send(400, {"error": "repo required"})
                return
            display_name = data.get("display_name", source_name)
            if not isinstance(display_name, str) or not display_name.strip():
                display_name = source_name
            entry = {"owner": owner.strip(), "repo": repo.strip(), "display_name": display_name.strip(), "enabled": enabled}
        cfg.setdefault(type_, {})[source_name] = entry
        try:
            _validate_config(cfg)
            save_config(cfg)
        except ConfigError as e:
            self._json_send(400, {"error": str(e)})
            return
        except OSError:
            self._json_send(500, {"error": "failed to write config"})
            return
        self._json_send(201, {source_name: entry})

    def do_PATCH(self):
        path = self.path.split("?", 1)[0].split("#", 1)[0].rstrip("/")
        parts = path.split("/")
        if len(parts) != 5 or parts[1] != "admin" or parts[2] != "sources":
            self.send_response(404)
            self.end_headers()
            return
        type_ = parts[3]
        source_name = parts[4]
        if type_ not in {"youtube", "reddit", "github"}:
            self._json_send(400, {"error": "unknown source type"})
            return
        if not re.match(r"^[a-zA-Z0-9_-]+$", source_name):
            self._json_send(400, {"error": "invalid source_name"})
            return
        cfg = load_config()
        section = cfg.get(type_, {})
        if source_name not in section:
            self._json_send(404, {"error": "source not found"})
            return
        content_len = int(self.headers.get("Content-Length", "0"))
        if content_len <= 0:
            # empty body -> unchanged
            self._json_send(200, {source_name: section[source_name]})
            return
        data = self._read_json_body()
        if data is None or data == "error":
            self._json_send(400, {"error": "invalid JSON body"})
            return
        entry = dict(section[source_name])
        # update provided fields
        if "enabled" in data:
            if not isinstance(data["enabled"], bool):
                self._json_send(400, {"error": "enabled must be bool"})
                return
            entry["enabled"] = data["enabled"]
        if type_ == "youtube":
            if "channel_id" in data:
                v = data["channel_id"]
                if not isinstance(v, str) or not v.strip():
                    self._json_send(400, {"error": "channel_id must be non-empty string"})
                    return
                entry["channel_id"] = v.strip()
            if "display_name" in data:
                v = data["display_name"]
                if not isinstance(v, str) or not v.strip():
                    self._json_send(400, {"error": "display_name must be non-empty string"})
                    return
                entry["display_name"] = v.strip()
        elif type_ == "reddit":
            if "subreddit" in data:
                v = data["subreddit"]
                if not isinstance(v, str) or not v.strip():
                    self._json_send(400, {"error": "subreddit must be non-empty string"})
                    return
                entry["subreddit"] = v.strip()
            if "display_name" in data:
                v = data["display_name"]
                if not isinstance(v, str) or not v.strip():
                    self._json_send(400, {"error": "display_name must be non-empty string"})
                    return
                entry["display_name"] = v.strip()
        else:
            if "owner" in data:
                v = data["owner"]
                if not isinstance(v, str) or not v.strip():
                    self._json_send(400, {"error": "owner must be non-empty string"})
                    return
                entry["owner"] = v.strip()
            if "repo" in data:
                v = data["repo"]
                if not isinstance(v, str) or not v.strip():
                    self._json_send(400, {"error": "repo must be non-empty string"})
                    return
                entry["repo"] = v.strip()
            if "display_name" in data:
                v = data["display_name"]
                if not isinstance(v, str) or not v.strip():
                    self._json_send(400, {"error": "display_name must be non-empty string"})
                    return
                entry["display_name"] = v.strip()
        cfg[type_][source_name] = entry
        try:
            _validate_config(cfg)
            save_config(cfg)
        except ConfigError as e:
            self._json_send(400, {"error": str(e)})
            return
        except OSError:
            self._json_send(500, {"error": "failed to write config"})
            return
        self._json_send(200, {source_name: entry})

    def do_DELETE(self):
        path = self.path.split("?", 1)[0].split("#", 1)[0].rstrip("/")
        parts = path.split("/")
        if len(parts) != 5 or parts[1] != "admin" or parts[2] != "sources":
            self.send_response(404)
            self.end_headers()
            return
        type_ = parts[3]
        source_name = parts[4]
        if type_ not in {"youtube", "reddit", "github"}:
            self._json_send(400, {"error": "unknown source type"})
            return
        if not re.match(r"^[a-zA-Z0-9_-]+$", source_name):
            self._json_send(400, {"error": "invalid source_name"})
            return
        cfg = load_config()
        section = cfg.get(type_, {})
        if source_name not in section:
            self._json_send(404, {"error": "source not found"})
            return
        del section[source_name]
        if not section:
            # keep empty dict or remove key? keep empty
            cfg[type_] = {}
        try:
            _validate_config(cfg)
            save_config(cfg)
        except ConfigError as e:
            self._json_send(400, {"error": str(e)})
            return
        except OSError:
            self._json_send(500, {"error": "failed to write config"})
            return
        self._json_send(200, {"ok": True, "source_name": source_name, "section": type_})

    def do_HEAD(self):
        # Minimal: reuse GET logic for the path check.
        self.do_GET()


def run_viewer(digest_dir: str = "digests", host: str = "0.0.0.0", port: int = 8000) -> int:
    """Start the digest web viewer. Returns 0 on clean shutdown."""
    _DigestHandler.digest_dir = Path(digest_dir).resolve()
    _DigestHandler.config_path = get_config_path()
    server = ThreadingHTTPServer((host, port), _DigestHandler)
    print(f"Serving digests from {_DigestHandler.digest_dir} on http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down viewer.")
    finally:
        server.server_close()
    return 0