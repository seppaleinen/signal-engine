import sys
from pathlib import Path
from signal_engine.store import Store
from signal_engine.sources.github_releases import fetch_all_sources as fetch_github
from signal_engine.sources.youtube import fetch_all_youtube
from signal_engine.sources.reddit import fetch_all_reddit
from signal_engine.filters import apply_filters

def run_all_sources(db_path: Path):
    store = Store(db_path)
    grand_inserted = 0
    
    print("=== GitHub releases ===")
    inserted, _ = run_source_group(store, fetch_github, "github")
    grand_inserted += inserted
    
    print("\n=== YouTube channels ===")
    inserted, _ = run_source_group(store, fetch_all_youtube, "youtube")
    grand_inserted += inserted
    
    print("\n=== Reddit subreddits ===")
    inserted, _ = run_source_group(store, fetch_all_reddit, "reddit")
    grand_inserted += inserted
    
    total = store.count_items()
    print(f"\nGrand total: {grand_inserted} inserted, {total} items in store")
    return grand_inserted, total

def run_source_group(store, fetcher, label):
    all_items = fetcher()
    inserted = 0
    for source_name, items in all_items.items():
        if not items:
            continue
        n = store.upsert_items(source_name, items)
        total = store.count_items(source_name)
        inserted += n
        print(f"  {source_name}: {len(items)} fetched, {n} inserted, {total} total")
    return inserted, 0

def run_stage3(db_path: Path):
    """
    Stage 3: Fetch items from all sources, apply code filters, report drops.
    Does NOT store items.
    """
    print("=== Stage 3: Code filters ===")
    all_items = {}
    
    # Fetch from each source (limited to avoid rate limits)
    print("\nFetching GitHub releases (max 10 per source)...")
    github_items = fetch_github(per_page=10)
    for src, items in github_items.items():
        all_items.setdefault(src, []).extend(items)
    
    print("Fetching YouTube (max 10 per channel)...")
    yt_items = fetch_all_youtube(per_page=10)
    for src, items in yt_items.items():
        all_items.setdefault(src, []).extend(items)
    
    print("Fetching Reddit (max 10 per subreddit)...")
    red_items = fetch_all_reddit(per_page=10)
    for src, items in red_items.items():
        all_items.setdefault(src, []).extend(items)
    
    # Apply filters per source
    grand_total = 0
    grand_kept = 0
    grand_drops = {'age':0, 'engagement':0, 'language':0, 'length':0}
    
    for source_name, items in all_items.items():
        if not items:
            continue
        kept, drops = apply_filters(items)
        kept_n = len(kept)
        total_n = len(items)
        grand_total += total_n
        grand_kept += kept_n
        for k in grand_drops:
            grand_drops[k] += drops.get(k, 0)
        print(f"  {source_name}: {total_n} -> kept {kept_n}, dropped {drops}")
    
    print(f"\n=== Summary ===")
    print(f"Total items fetched: {grand_total}")
    print(f"Kept after filters: {grand_kept}")
    print(f"Dropped by age: {grand_drops['age']}")
    print(f"Dropped by engagement: {grand_drops['engagement']}")
    print(f"Dropped by language: {grand_drops['language']}")
    print(f"Dropped by length: {grand_drops['length']}")
    return grand_kept, grand_total

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="data/signal.db", help="Path to SQLite DB")
    parser.add_argument("--stage3", action="store_true", help="Run Stage 3 (filters) and exit")
    parser.add_argument("--stage4", action="store_true", help="Run Stage 4 (decision pass) on a sample and exit")
    args = parser.parse_args()
    
    db_path = Path(args.db)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    
    if args.stage3:
        run_stage3(db_path)
        return 0
    
    if args.stage4:
        # Run decision pass on a sample
        import asyncio
        from signal_engine.store import Store
        store = Store(db_path)
        
        # Grab sample items from store (recent ones)
        sample = []
        for src in ["opencode-releases", "litellm-releases", "betterstack"]:
            rows = store.get_items(src, limit=5)
            for id_, title, url, published in rows:
                sample.append({
                    "id": id_,
                    "source": src,
                    "title": title,
                    "url": url,
                    "body": "",
                    "published_at": published
                })
        
        print(f"Testing decision pass on {len(sample)} items...")
        from signal_engine.decision import USE_REAL_LLM
        if USE_REAL_LLM:
            print("Using real LiteLLM decision model (freellmapi)")
        else:
            print("Note: Using mock decision logic (no LLM endpoint configured). Configure LITELLM_BASE_URL in .env to use real model.")
        print()
        
        from signal_engine.decision import decide_batch
        results = asyncio.run(decide_batch(sample))
        
        kept = 0
        dropped = 0
        unsure = 0
        for item, scores, route in results:
            print(f"[{route.upper():6}] rel={scores['relevance']:.2f} new={scores['new']:.2f} | {item['title'][:80]}")
            if route == "keep":
                kept += 1
            elif route == "drop":
                dropped += 1
            else:
                unsure += 1
        
        print(f"\nSummary: kept {kept}, dropped {dropped}, unsure {unsure}")
        print("\nNext: Configure LITELLM_BASE_URL in .env to run real LLM decision pass.")
        return 0
    
    inserted, total = run_all_sources(db_path)
    
    # Prove deduplication by running again
    print("\n--- Re-run to prove dedupe ---")
    inserted_2, _ = run_all_sources(db_path)
    
    if inserted_2 == 0:
        print("\n✓ Dedup works: re-run added 0 items")
    else:
        print(f"\n⚠ Re-run added {inserted_2} new items")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())