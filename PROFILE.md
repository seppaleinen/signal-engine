# Signal engine profile

<!-- Written by the build-signal-engine interview. Every stage reads this file. Edit it
     freely; the engine follows it. -->

## What I keep up with

<!-- R1.1: the focus, and what I do differently when I know on the day. -->

Practical AI-for-coding: building systems with AI, and optimizing the workflows around it.
I want to find out about new tools, releases, and hands-on tricks the day they appear —
so I can try or adopt them that week, not months later.

## Sources

<!-- R2.2: where people using those tools actually talk. -->
Data platform: picked per source (R2.6)

| Source | What it is | How it is pulled | Why it is here |
|---|---|---|---|
| YouTube channels | AI-coding workflows, quantization, new tools | YouTube RSS (free) | R1.2: found gsq-rco + qwen3.8 here first |
| Reddit (r/LocalLLM, r/MachineLearning, etc.) | Community findings, fixes, workflows | Reddit RSS (free, 429-retry) | R2.2: where users of my tools talk |
| OpenCode changelog/releases | Coding agent updates | GitHub Releases API (anomalyco/opencode) | R2.1: daily tool |
| LM Studio / llama-swap / llama.cpp releases | Local model serving | GitHub Releases API (ggml-org/llama.cpp, lmstudio-ai/lms) | R2.1: daily tools |
| Hindsight, LiteLLM, similar tools | New tools in the AI-coding stack | GitHub Releases API (vectorize-io/hindsight, BerriAI/litellm) | R2.3 keep example: new tools |
| Quantization repos (e.g. gsq-rco) | Model compression that fits my 16GB | to be implemented (Stage 2) | R1.2 example: qwen3.8 + gsq-rco |

## Code filters

<!-- R2.4: facts only. Age, engagement floor, language, length. Each one a number. -->
- Max age: 7 days (older is history)
- Engagement floor: Reddit posts below a rough upvote threshold (tuned in shadow week)
- Language: English only
- Length: skip one-liners with no substance

## The decision question(s)

<!-- One thing per question. Written from the examples below, in my words. -->

1. **Relevance (score 0–1):** Is this about practical AI-for-coding — building systems with AI,
   optimizing AI workflows, or a new tool in that stack?
2. **Reports something new and concrete (yes/no):** Does this report a specific, actionable
   finding (a release, a trick, a tool, a quantization method) rather than hype, a benchmark,
   or a paper without immediate implementation?

**Routing:**
- Drop when: clearly off-topic (score < 0.3) OR not new/concrete (no) AND not a paper I can implement
- Keep when: clearly relevant (score ≥ 0.7) AND new/concrete (yes)
- Everything else (uncertain middle) goes to the reading pass

<!-- R2.5: which is worse, missing something big or wasting my time? -->
Preference: **missing something big is worse** — I'd rather see one extra item than miss a deprecation or a key trick.

### Keep examples
<!-- R2.3: things I would have wanted, with a link if I have one. -->
- The gsq-rco compression method that lets qwen3.8-27b run on a 16GB GPU (R1.2)
- A workflow trick that makes AI-assisted coding faster (e.g. a new agent pattern)
- An OpenCode or LM Studio release/change
- A new tool like Hindsight or LiteLLM that fits the AI-coding stack

### Drop examples
<!-- R2.3: things I never want to see again. -->
- Research papers that aren't immediately implementable
- General AI hype or benchmark PR with no actionable takeaway
- Non-AI coding news

## The digest

- Where I read it: `digests/YYYY-MM-DD.md` in this repo (markdown note)
- Length cap: 10 items
- Format: grouped by theme, 1–2 sentences per item, every link kept
- Extras: none for now; can add a "to-try" list section later

## Schedule

- Full run: daily, 07:30 local time
- Shadow week: on — start after Stage 5, run for 7 days while I mark misses and noise
- LLM endpoint: LiteLLM proxy (URL to be added to env file by user)