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

Planned: daily run at 07:30 local time. For Kubernetes (k3s) deployment, see
[issue #1](https://github.com/seppaleinen/signal-engine/issues/1).
