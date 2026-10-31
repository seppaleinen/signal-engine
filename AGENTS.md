<!-- trail:start -->
## Trail — repo context graph

This repo is indexed in `.trail/cache/`: small linked markdown nodes that explain each
system and carry exact file:line spans, kept in sync with the code through git.

For ANY task here — understanding how something works, finding where code lives,
or scoping a change — get context from the graph before grepping or opening
source files. Re-ask freely (it's cheap) and reuse literal identifiers you
already have (symbol, error string, file name) as the query. New to this repo?
Run `trail map` first — a token-budgeted orientation (dir clusters, hubs,
hotspots), no LLM, no key.

- Run `trail ask "<your question>" --source` → ranked nodes with the relevant
  code spans inlined (each hit's ≤8-line crux by default; `--full` for whole
  definitions when the crux isn't enough). Match the tool to the task shape:
  for understanding or editing, the top node IS the answer — cite its
  `covers:` file:line spans and edit straight from `--source`. For
  exhaustive tasks ("every occurrence / every caller of this pattern"), ranked
  results are top-N, not complete — run `trail grep "<literal>"` instead
  (exhaustive over indexed files, grouped by enclosing symbol), falling back
  to raw `grep -rn` only for unindexed files.
- `trail skeleton <file>` → every definition's signature + span, ~10× cheaper
  than reading the file; use it to skim an API surface.
- `trail callers <symbol>` gives precomputed, exact edges — who calls this.
  Add `--depth N` to walk transitively for the full blast radius.
- Or browse: `.trail/cache/INDEX.md` lists every node; follow the links.
- Monorepos and folders of multiple repos rank fairly across sub-projects —
  hits carry `[scope/]` labels naming which one they're from. Narrow with
  `trail ask "<task>" --in <scope>/` once you know where you're working.

If a returned span is truncated ("+N more lines"), open the file at that exact
range before finalizing. Only open source files when a node genuinely lacks a
needed detail, and then at the exact file:line the node points to — never
re-read whole files.

After big code changes, refresh the graph with `trail build` (deterministic,
no API key, $0).
<!-- trail:end -->

---

## Agent Coordination

This project uses a structured pipeline system for coordinating work. All changes flow through defined pipeline leads.

### Available Subagents

| Agent | Purpose |
|-------|---------|
| `researcher` | Investigate raw/ambiguous requests and create a Research Brief |
| `dev-team-lead` | Manage application development: design, implementation, testing, review |
| `devops-team-lead` | Manage infrastructure: GitOps, Kubernetes, containers, deployment |
| `post-mortem-analyst` | Analyze workflow after verification, propose improvements |
| `devops-cleanup` | Post-deployment cleanup: close issues, delete branches |

### Task Classification

Classify incoming tasks as:

- **Dev work**: Application code changes, features, bug fixes, tests, UI
- **DevOps work**: Infrastructure, Flux/GitOps, Kubernetes, containers, CI/CD
- **Mixed**: Both dev and ops (dispatch in parallel)

### Dispatch Pattern

Use the `subagent()` tool to dispatch work:

```
subagent(
  description="<task summary>",
  prompt="<research brief path + constraints + expected output>",
  agent="dev-team-lead" | "devops-team-lead" | "researcher"
)
```

**What to include in prompt:**
- The Research Brief file path (from researcher)
- Summary of key constraints
- Expected output format

**What NOT to include:**
- Full conversation history
- Raw tool output
- Internal routing logic

---

## Pipeline Leads

### dev-team-lead Workflow

1. **Design**: `dev-architect` creates design document
2. **Implementation**: `backend-engineer` or `frontend-engineer` writes code
3. **Verification**: `test-engineer` or `code-reviewer` validates
4. **Security**: `ai-security-auditor` reviews

### devops-team-lead Workflow

1. **Design**: `devops-architect` creates design document
2. **Implementation**: `devops-engineer` writes code
3. **Verification**: `devops-verificator` validates
4. **Security**: `ai-security-auditor` reviews

---

## Pipeline Visibility

The `pipeline-visibility` skill implements status reporting:
- Announce before every dispatch
- Report after every return
- Surface STUCK/REWORK/BLOCK states with reasons

Load it at the start:
```
skill(name="pipeline-visibility")
```

---

## Rework Handling

The `rework-handling` skill governs:
- `task_id` capture for resume
- Maximum 2 retries
- BLOCK escalation on persistent failures
- REWORK_COUNT tracking

Load it early:
```
skill(name="rework-handling")
```

---

## Tool Usage Rules (Code Mode Guardrail)

Before any direct execution:

| Tool | Use For | NOT For |
|------|---------|---------|
| `execute` | Pure JS: `JSON.parse()`, math, string manipulation | Shell commands, `require()`, `process`, `fs`, `Buffer`, `child_process`, git, file I/O |
| `shell` | CLI commands: `git`, `find`, `grep`, `kubectl`, `flux`, `curl`, `node` | Pure JS computation |
| `read`/`write`/`edit` | File operations in workspace | Shell redirections (`cat >`, `tee`), inline file creation |

---

## Delegation Convention

Load the delegation contract for inter-agent communication:
```
skill(name="delegation-contract")
```

This enforces:
- subagent()-only dispatch (no direct worker dispatch)
- subagent_depth=2 cap
- Handover protocol with TRACE, PIPELINE STAGE, STATUS fields

---

## Expected Handover Format

All agents must return structured handovers:

```
STATUS: [SUCCESS] | [REWORK] | [BLOCK] | [STUCK]
TRACE: team-lead -> dev-team-lead -> dev-architect -> backend-engineer -> ...
PIPELINE STAGE: design -> implement -> verify -> security

<BLOCK headers>:
<error details and required actions>

<SUCCESS content>:
- What was done
- Key decisions
- Files changed
- Next steps
```

---

## Project Structure

```
signal-engine/
├── src/signal_engine/     # Main package
│   ├── cli.py             # CLI entry point
│   ├── config.py          # Config loading/validation
│   ├── decision.py        # LLM decision logic
│   ├── digest_html.py     # HTML digest renderer
│   ├── filters.py         # Code filters (age, engagement, language, length)
│   ├── reading.py         # LLM reading pass & digest generation
│   ├── sources/           # Source adapters
│   │   ├── github_releases.py
│   │   ├── reddit.py
│   │   ├── rss.py
│   │   └── youtube.py
│   ├── store.py           # SQLite store
│   └── viewer.py          # HTTP viewer
├── charts/signal-engine/  # Helm chart
├── config/                # YAML source configuration
├── scripts/               # Release scripts
├── tests/                 # Test files
└── digests/               # Generated digests (gitignored)
```

---

## Development Conventions

### Testing

- Location: `tests/`
- Framework: pytest
- Run: `uv run pytest`
- Tests follow HTTP contract testing pattern (status, headers, body)

### Linting

- `uv run ruff check .`
- `uv run ruff format --check .`

### Commits

- Conventional commit format: `type: subject`
- Skip CI: `[skip ci]` in message
- Release commits: `[skip ci]` to avoid self-triggering

### CI/CD

- Push to `main` → auto-release (patch bump)
- Push tag `vX.Y.Z` → manual release
- Requires `GHCR_TOKEN` with `write:packages`, `read:packages`, `contents:write`

---

## Security Requirements

See `docs/adr/0001-signal-engine-015-security-hardening.md` for complete details:

1. Non-root execution (container runs as user 1000)
2. Container hardening (read-only root FS, no privilege escalation)
3. Image digest pinned in production
4. NetworkPolicy restricts ingress

### Data Protection

- `data/signal.db` (SQLite) is gitignored
- `digests/` directory is gitignored  
- `.env` files are gitignored
- Secrets never baked into images

---

## Common Patterns

### Adding a New Source Type

1. Create `src/signal_engine/sources/<type>.py` with `fetch_all_<type>()` function
2. Add to `cli.py` `fetch_all()` function
3. Add to `config.py` validation
4. Add to `viewer.py` admin API and UI
5. Add to `sources.yaml` schema documentation

### Modifying the Digest Format

1. Update `reading.py` prompt
2. Update `digest_html.py` renderer
3. Update mock/fallback examples
4. Test with `--stage4` flag

---

<!-- trail:end -->