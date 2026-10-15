# Stage 4 Summary: The Decision Pass

## What was done
- Implemented the decision pass with two questions from PROFILE.md:
  1. **Relevance (score 0-1)**: Is this about practical AI-for-coding — building systems with AI, optimizing AI workflows, or a new tool in that stack?
  2. **Reports something new and concrete (probability 0-1)**: Does this report a specific, actionable finding (a release, a feature, a tool, a measured result, a technique, a documented incident)?

- Routing logic:
  - **drop** when relevance < 0.4 OR new < 0.1
  - **keep** when relevance >= 0.5 AND new >= 0.6
  - **unsure** everything else (goes to reading pass)

- Integrated with LiteLLM proxy using `freellmapi` model
- Tested on 10 items from the store (GitHub releases)

## Results
```
[KEEP  ] rel=0.90 new=1.00 | v1.19.0
[DROP  ] rel=0.20 new=0.90 | v1.18.35
[KEEP  ] rel=0.80 new=0.90 | v1.18.34
[DROP  ] rel=0.00 new=1.00 | v1.18.33
[DROP  ] rel=0.20 new=0.90 | v1.18.32
[KEEP  ] rel=0.90 new=0.80 | v1.107.0-dev.2
[KEEP  ] rel=0.95 new=1.00 | v1.106.0-rc.3
[KEEP  ] rel=0.80 new=0.90 | v1.107.0-dev.1
[KEEP  ] rel=0.90 new=0.95 | v1.105.1
[UNSURE] rel=0.90 new=0.50 | v1.106.0-rc.2

Summary: kept 6, dropped 3, unsure 1
```

The decision pass is working. Some releases are being dropped because the model judges them as not relevant (rel < 0.4) despite being new. The "unsure" items go to the reading pass.

## Files changed
- `src/signal_engine/decision.py` – decision pass implementation
- `src/signal_engine/cli.py` – added `--stage4` flag

## Next (Stage 5)
- The reading pass + digest: LLM reads only the items that survived the filters and decision pass, groups them, and writes the digest in the format from PROFILE.md
- Cap the digest at 10 items
- Deliver to `digests/YYYY-MM-DD.md`

## Notes
- LiteLLM credentials are loaded from environment variables `LITELLM_BASE_URL` and `LITELLM_API_KEY` (already configured in the environment)
- Mock decision logic is available as fallback when LLM endpoint is not configured
- The decision pass never drops on error — failed calls route to "unsure"
