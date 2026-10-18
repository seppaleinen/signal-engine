# Signal Engine

A personal signal engine that reads AI-coding news every day: pulls from GitHub releases,
YouTube channels and Reddit, filters by code (age, engagement, language, length), runs a
decision pass (LLM, two typed questions), and writes a 10-item digest.

Focus: practical AI-for-coding — building systems with AI, optimizing AI workflows,
new tools in that stack. See `PROFILE.md` for the full spec.

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
| `image.repository` | `seppaleinen/signal-engine` | Override the image |
| `image.tag` | `latest` | Override the tag |

## Releasing (automated)

- **Auto release on main:** Push to `main` triggers a patch bump, builds the Docker image
  `seppaleinen/signal-engine:<version>` (+ `:latest`), tags the chart, and creates a
  GitHub Release `chart/v<version>` with asset `signal-engine-<version>.tgz`.

- **Manual minor/major:** Push a tag `vX.Y.Z` to manually release a specific version.
  The workflow validates the tag, converges the chart files, builds & pushes the image,
  and releases the chart.

- **Secrets required:** `DOCKERHUB_USERNAME` and `DOCKERHUB_TOKEN` (Docker Hub).

- **Consume:** Replace `<version>` below; chart archives are named
  `signal-engine-<version>.tgz` and released under tag `chart/v<version>`:

```bash
helm install signal-engine \
  https://github.com/seppaleinen/signal-engine/releases/download/chart/v0.1.0/signal-engine-0.1.0.tgz \
  --namespace signal-engine
```

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
