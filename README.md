# Signal Engine

A personal signal engine that reads AI-coding news every day: pulls from GitHub releases,
YouTube channels and Reddit, filters by code (age, engagement, language, length), runs a
decision pass (LLM, two typed questions), and writes a 10-item digest.

Focus: practical AI-for-coding — building systems with AI, optimizing AI workflows,
new tools in that stack. See `PROFILE.md` for the full spec.

## Table of Contents

- [Quick start (Docker)](#quick-start-docker)
- [Without Docker](#without-docker)
- [Pipeline](#pipeline)
- [Sources](#sources)
- [Configuration](#configuration)
- [Kubernetes (k3s) deployment](#kubernetes-k3s-deployment)
- [Web viewer](#web-viewer)
- [Testing](#testing)
- [Development](#development)
- [Troubleshooting](#troubleshooting)
- [Releases (automated)](#releases-automated)

## Quick start (Docker)

Build the image:

```bash
docker build -t signal-engine:latest .
```

Run once:

```bash
docker run --rm \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/digests:/app/digests \
  -e LITELLM_BASE_URL=https://litellm.labb.site/v1 \
  -e LITELLM_API_KEY=your-key \
  signal-engine:latest --run
```

The digest lands in `digests/YYYY-MM-DD.md`.

Or with compose:

```bash
LITELLM_API_KEY=... docker compose up
```

### Notes

- A full run takes several minutes: it makes one LLM call per item in the decision pass.
- `data/signal.db` (SQLite) holds the store; re-runs are deduplicated by stable id.
- If the reading-pass LLM call fails, the engine writes a fallback list digest and
  still exits 0 — the run never loses its digest.
- Secrets are passed as env vars at run time; nothing is baked into the image.

## Without Docker

```bash
uv sync
uv run signal-engine --run          # full pipeline
uv run signal-engine --stage3      # fetch + code filters report
uv run signal-engine --stage4      # decision pass on a sample
```

Requires `LITELLM_BASE_URL` and `LITELLM_API_KEY` in the environment (or a gitignored
`.env` file).

## Pipeline

```
sources -> store (SQLite, dedupe, stable ids) -> code filters
       -> decision pass (LLM, two questions, parallel) -> reading pass (one LLM call)
       -> digests/YYYY-MM-DD.md
```

- **Sources:** GitHub releases (OpenCode, llama-swap, Hindsight, LiteLLM, LM Studio),
  YouTube RSS (betterstack, AI Engineer, Fireship), Reddit RSS (r/LocalLLM,
  r/MachineLearning). All free; Reddit is rate-limited and retried.
- **Code filters:** max age 7 days, engagement floor, English only, min length.
- **Decision pass:** relevance score + "new and concrete" probability. Drops only when
  clearly off-topic; uncertain items go to the reading pass.
- **Digest:** ≤10 items, grouped, one or two sentences each, every link kept.

## Sources

Sources are configured in `config/sources.yaml`. Three source types are supported:

| Type | Config fields | Description |
|------|--------------|-------------|
| `youtube` | `channel_id`, `display_name`, `enabled` | YouTube channel RSS feeds (video thumbnails extracted via `media:thumbnail`) |
| `reddit` | `subreddit`, `display_name`, `enabled` | Reddit subreddit RSS feeds (previews extracted) |
| `github` | `owner`, `repo`, `display_name`, `enabled` | GitHub release APIs (repo avatar used as thumbnail) |
| `rss` | `feed_url`, `display_name`, `enabled` | Generic RSS/Atom feeds (thumbnail from `media:thumbnail`) |

Each source can be enabled/disabled. Items are deduplicated by a stable id derived from URL/title.

## Configuration

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `LITELLM_BASE_URL` | Yes (unless using mock mode) | URL to your LiteLLM proxy |
| `LITELLM_API_KEY` | Yes | API key for LiteLLM |
| `SIGNAL_ENGINE_CONFIG` | No | Path to custom sources.yaml (default: `config/sources.yaml` in repo root) |

### Docker Compose

A `docker-compose.yml` file is provided with two services:

- **signal-engine**: Builds and runs the full pipeline (fetch → filters → decision → digest). Exits after one run.
- **signal-engine-viewer**: Long-running sidecar that serves HTML digests at `http://localhost:8080/`.

```bash
# Build and start both services
docker compose up

# View the digest
open http://localhost:8080/
```

### Data Directory Structure

- `data/signal.db` - SQLite store with all fetched items
- `digests/YYYY-MM-DD.md` - Markdown digest for each day
- `digests/YYYY-MM-DD.html` - Pre-rendered HTML version

## Schedule

Planned: daily run at 07:30 local time.

## Kubernetes (k3s) deployment

A Helm chart lives in `charts/signal-engine/`. It follows the sidecar architecture
established in [issue #2](https://github.com/seppaleinen/signal-engine/issues/2):

- **CronJob** (`signal-engine-run`) runs `signal-engine --run` daily at 07:30 local
  time. Writes to the `digests` PVC.
- **Deployment** (`signal-engine-viewer`) runs `signal-engine --viewer` as a
  long-running sidecar. Serves digests via the Service + Ingress and shares the
  `digests` PVC so it immediately sees job output.
- **PVCs** for `data/` (SQLite store) and `digests/`.

### Install

```bash
# From the repo (local chart)
helm install signal-engine ./charts/signal-engine \
  --namespace signal-engine \
  --set secret.litellmBaseUrl=https://your-llm/v1 \
  --set secret.litellmApiKey=YOUR-KEY

# Or from the published chart (GitHub Release)
helm install signal-engine https://github.com/seppaleinen/signal-engine/releases/download/chart/v0.1.0/signal-engine-0.1.0.tgz \
  --namespace signal-engine \
  --set secret.litellmBaseUrl=https://your-llm/v1 \
  --set secret.litellmApiKey=YOUR-KEY
```

The viewer is then reachable at the Ingress host (default `signal-engine.local` —
override with `--set ingress.hosts[0].host=viewer.example.com`).

### Credentials

The Secret manifest ships with **placeholder values** only. Never commit real
credentials. Set them at install time with `--set` (as above), pre-create the
secret with `kubectl`, or use external-secrets:

```bash
kubectl create secret generic signal-engine-secret \
  --from-literal=LITELLM_BASE_URL=https://your-llm/v1 \
  --from-literal=LITELLM_API_KEY=YOUR-KEY \
  --namespace signal-engine
```

### Options

| Value | Default | Notes |
|---|---|---|
| `cronJob.enabled` | `true` | Disable the daily run |
| `ingress.enabled` | `true` | Disable if no ingress controller |
| `persistence.enabled` | `true` | Disable PVCs (stateless) |
| `persistence.storageClassName` | cluster default | Pin a storage class |
| `cronJob.schedule` | `30 7 * * *` | Cron expression |
| `cronJob.timezone` | cluster TZ | e.g. `Europe/Helsinki` |
| `image.repository` | `ghcr.io/seppaleinen/signal-engine` | Override the image |
| `image.tag` | `latest` | Override the tag |

## Releasing (automated)

- **Auto release on main:** Push to `main` triggers a patch bump, builds the Docker image
  `ghcr.io/seppaleinen/signal-engine:<version>` (+ `:latest`), tags the chart, and creates a
  GitHub Release `chart/v<version>` with asset `signal-engine-<version>.tgz`.

- **Manual minor/major:** Push a tag `vX.Y.Z` to manually release a specific version.
  The workflow validates the tag, converges the chart files, builds & pushes the image,
  and releases the chart.

- **Secrets required:** `GHCR_TOKEN` — a classic personal access token with
  `write:packages`, `read:packages`, and `contents:write` scopes. The token is used
  for both GHCR image push and committing version bumps back to `main`.
  The default `GITHUB_TOKEN` cannot push to GHCR for a personal user account —
  a dedicated PAT is required.

- **Consume:** Replace `<version>` below; chart archives are named
  `signal-engine-<version>.tgz` and released under tag `chart/v<version>`:

```bash
helm install signal-engine \
  https://github.com/seppaleinen/signal-engine/releases/download/chart/v0.1.0/signal-engine-0.1.0.tgz \
  --namespace signal-engine
```

## Options

| Value | Default | Notes |
|---|---|---|
| `cronJob.enabled` | `true` | Disable the daily run |
| `ingress.enabled` | `true` | Disable if no ingress controller |
| `persistence.enabled` | `true` | Disable PVCs (stateless) |
| `persistence.storageClassName` | cluster default | Pin a storage class |
| `persistence.data.size` | `1Gi` | Size of the SQLite database PVC |
| `persistence.digests.size` | `1Gi` | Size of the digests PVC |
| `persistence.digests.accessModes` | `["ReadWriteMany"]` | Usually ReadWriteMany for shared access |
| `cronJob.schedule` | `30 7 * * *` | Cron expression (07:30 daily) |
| `cronJob.timezone` | cluster TZ | e.g. `Europe/Helsinki` |
| `image.repository` | `ghcr.io/seppaleinen/signal-engine` | Override the image |
| `image.tag` | `latest` | Override the tag |
| `image.pullPolicy` | `IfNotPresent` | Image pull policy |
| `viewer.replicas` | `1` | Number of viewer pods |
| `viewer.port` | `8000` | Viewer HTTP port |
| `viewer.resources` | cpu 50m/250m, memory 128Mi/256Mi | Viewer resource limits |
| `cronJob.resources` | cpu 200m/1, memory 256Mi/512Mi | CronJob resource limits |
| `ingress.hosts[0].host` | `signal-engine.local` | Ingress hostname |
| `configMap.sourcesYaml` | (from config/sources.yaml) | Override with custom sources YAML |

## Testing

Run the test suite with pytest:

```bash
uv sync  # install with test dependencies
uv run pytest
```

Tests cover HTTP contract for the viewer (GET, HEAD, path traversal, etc.).

## Development

### Prerequisites

- Python 3.13+ (or use the Docker image)
- `uv` package manager
- LiteLLM endpoint (for full pipeline; mock mode available)

### Setup

```bash
# Clone and install
git clone https://github.com/seppaleinen/signal-engine.git
cd signal-engine
uv sync

# Run locally (without Docker)
uv run signal-engine --run

# Start viewer only
uv run signal-engine --viewer --port 8000
```

### Lint

```bash
uv run ruff check .
uv run ruff format --check .
```

### Add a new source

1. Edit `config/sources.yaml`:

```yaml
sources:
  your-source:
    feed_url: "https://example.com/feed.xml"
    display_name: "My Source"
    enabled: true
```

2. For YouTube, Reddit, or GitHub, adjust the fields accordingly:

```yaml
youtube:
  my-channel:
    channel_id: "UCxxxxxxxxx"
    display_name: "My Channel"
    enabled: true

rss:
  my-feed:
    feed_url: "https://example.com/feed.xml"
    display_name: "My Feed"
    enabled: true
```

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `tldr: FAILED - Non-RSS response` | The Kill-the-Newsletter feed URL needs to be set up. Visit https://kill-the-newsletter.com, generate an email, subscribe to TLDR, and use the feed URL. |
| `sources.yaml not found` | Mount the ConfigMap via Helm chart (v0.1.10+) or set `SIGNAL_ENGINE_CONFIG` env var |
| `Connection refused`/`Timeout` | Verify `LITELLM_BASE_URL` is reachable from the container/cluster |
| `No items in digest` | Check that sources have recent items (max age filter is 7 days) |
| `Image pull failed on arm64` | v0.1.10+ is multi-platform; older tags may be architecture-specific |

## Web viewer

A long-running sidecar serves the digests over HTTP. With Docker Compose:

```bash
docker compose up
```

- `signal-engine` runs once (`--run`), writes `digests/YYYY-MM-DD.md` + `.html`, then exits.
- `signal-engine-viewer` stays up and serves at `http://localhost:8080/`.

HTML is generated alongside markdown for every new digest. Legacy md-only digests
(e.g. `2026-10-15.md`) are rendered on the fly when requested.

Local (non-Docker) usage:

```bash
uv run signal-engine --viewer --port 8000
```
