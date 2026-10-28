"""Config loader / saver for signal-engine sources.

Implements a minimal YAML subset parser/serializer for the 2-level
sources.yaml format. Stdlib-only.
"""

from __future__ import annotations

import os
import re
import signal as _signal
from pathlib import Path
from typing import Any, Dict

_config_cache: Dict[str, Any] | None = None


class ConfigError(Exception):
    """Raised for missing or malformed configuration."""


def get_config_path() -> Path:
    env = os.environ.get("SIGNAL_ENGINE_CONFIG")
    if env:
        return Path(env)
    # repo root = parent of package's parent
    repo_root = Path(__file__).resolve().parent.parent.parent
    return repo_root / "config" / "sources.yaml"


def _parse_value(raw: str) -> Any:
    raw = raw.strip()
    if not raw:
        return ""
    if raw.startswith('"') and raw.endswith('"'):
        # minimal unescape for \" and \\
        inner = raw[1:-1]
        inner = inner.replace(r'\"', '"').replace(r'\\', '\\')
        return inner
    if raw == "true":
        return True
    if raw == "false":
        return False
    return raw


def _parse_sources_yaml(text: str) -> Dict[str, Any]:
    """Parse minimal 2-level YAML subset used for sources.yaml.

    Supports 2-space indentation, key: or key: value lines,
    string values optionally quoted, and true/false booleans.
    """
    cfg: Dict[str, Any] = {}
    # stack of (dict, indent)
    stack: list[tuple[Dict[str, Any], int]] = [(cfg, -1)]

    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" "))
        if indent % 2 != 0:
            # allow but treat as error later
            pass
        stripped = line.lstrip(" ")
        if ":" not in stripped:
            continue
        key_part, sep, rest = stripped.partition(":")
        key = key_part.strip()
        rest = rest.strip()

        # pop stack to correct parent
        while stack and indent <= stack[-1][1]:
            stack.pop()
        parent, _ = stack[-1]

        if rest == "":
            # map node
            new_dict: Dict[str, Any] = {}
            parent[key] = new_dict
            stack.append((new_dict, indent))
        else:
            parent[key] = _parse_value(rest)

    return cfg


def _dump_value(v: Any) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, str):
        # always quote strings for stability
        esc = v.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{esc}"'
    return str(v)


def _dump_dict(d: Dict[str, Any], indent: int = 0) -> list[str]:
    lines: list[str] = []
    prefix = "  " * indent
    for key, val in d.items():
        if isinstance(val, dict):
            lines.append(f"{prefix}{key}:")
            lines.extend(_dump_dict(val, indent + 1))
        else:
            lines.append(f"{prefix}{key}: {_dump_value(val)}")
    return lines


def _dump_sources_yaml(cfg: Dict[str, Any]) -> str:
    lines = _dump_dict(cfg, 0)
    return "\n".join(lines) + "\n"


def _validate_config(config: Dict[str, Any]) -> None:
    allowed_sections = {"youtube", "reddit", "github", "rss"}
    if not isinstance(config, dict):
        raise ConfigError("Config root must be a mapping")

    for sec in config:
        if sec not in allowed_sections:
            raise ConfigError(f"Unknown top-level section: {sec}")

    name_re = re.compile(r"^[a-zA-Z0-9_-]+$")

    for sec, entries in config.items():
        if not isinstance(entries, dict):
            raise ConfigError(f"Section {sec} must be a mapping")
        for name, entry in entries.items():
            if not isinstance(name, str) or not name_re.match(name):
                raise ConfigError(f"Invalid entry name {name!r} in {sec}")
            if not isinstance(entry, dict):
                raise ConfigError(f"Entry {name} in {sec} must be a mapping")
            # enabled
            if "enabled" in entry:
                if not isinstance(entry["enabled"], bool):
                    raise ConfigError(f"enabled must be bool for {sec}/{name}")
            # required fields
            if sec == "youtube":
                for field in ("channel_id", "display_name"):
                    v = entry.get(field)
                    if not isinstance(v, str) or not v.strip():
                        raise ConfigError(f"{sec}/{name} missing non-empty {field}")
            elif sec == "reddit":
                for field in ("subreddit", "display_name"):
                    v = entry.get(field)
                    if not isinstance(v, str) or not v.strip():
                        raise ConfigError(f"{sec}/{name} missing non-empty {field}")
            elif sec == "github":
                for field in ("owner", "repo"):
                    v = entry.get(field)
                    if not isinstance(v, str) or not v.strip():
                        raise ConfigError(f"{sec}/{name} missing non-empty {field}")
                # display_name optional
                if "display_name" in entry and not isinstance(entry["display_name"], str):
                    raise ConfigError(f"{sec}/{name} display_name must be string")
            elif sec == "rss":
                for field in ("feed_url", "display_name"):
                    v = entry.get(field)
                    if not isinstance(v, str) or not v.strip():
                        raise ConfigError(f"{sec}/{name} missing non-empty {field}")


def _load_and_validate(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        raise ConfigError(f"Config file not found: {path}")
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        raise ConfigError(f"Cannot read config: {e}") from e
    cfg = _parse_sources_yaml(text)
    _validate_config(cfg)
    return cfg


def load_config() -> Dict[str, Any]:
    global _config_cache
    if _config_cache is not None:
        return _config_cache
    path = get_config_path()
    cfg = _load_and_validate(path)
    _config_cache = cfg
    return cfg


def reload_config() -> None:
    global _config_cache
    _config_cache = None


def _is_enabled(entry: Dict[str, Any]) -> bool:
    return bool(entry.get("enabled", True))


def get_youtube_channels() -> Dict[str, Dict[str, str]]:
    cfg = load_config()
    out: Dict[str, Dict[str, str]] = {}
    for name, entry in cfg.get("youtube", {}).items():
        if not _is_enabled(entry):
            continue
        out[name] = {
            "channel_id": entry["channel_id"],
            "display_name": entry["display_name"],
        }
    return out


def get_reddit_subreddits() -> Dict[str, Dict[str, str]]:
    cfg = load_config()
    out: Dict[str, Dict[str, str]] = {}
    for name, entry in cfg.get("reddit", {}).items():
        if not _is_enabled(entry):
            continue
        out[name] = {
            "subreddit": entry["subreddit"],
            "display_name": entry["display_name"],
        }
    return out


def get_github_sources() -> Dict[str, Dict[str, str]]:
    cfg = load_config()
    out: Dict[str, Dict[str, str]] = {}
    for name, entry in cfg.get("github", {}).items():
        if not _is_enabled(entry):
            continue
        out[name] = {
            "owner": entry["owner"],
            "repo": entry["repo"],
            "display_name": entry.get("display_name", name),
        }
    return out


def get_rss_sources() -> Dict[str, Dict[str, str]]:
    cfg = load_config()
    out: Dict[str, Dict[str, str]] = {}
    for name, entry in cfg.get("rss", {}).items():
        if not _is_enabled(entry):
            continue
        out[name] = {
            "feed_url": entry["feed_url"],
            "display_name": entry["display_name"],
        }
    return out


def save_config(config: Dict[str, Any]) -> None:
    _validate_config(config)
    path = get_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp_path.write_text(_dump_sources_yaml(config), encoding="utf-8")
        os.replace(tmp_path, path)
    except OSError as e:
        raise ConfigError(f"Cannot write config: {e}") from e
    reload_config()


def install_sighup_handler() -> None:
    if hasattr(_signal, "SIGHUP"):
        try:
            _signal.signal(_signal.SIGHUP, lambda *_: reload_config())
        except (ValueError, OSError):
            # signal already set or not permitted
            pass
