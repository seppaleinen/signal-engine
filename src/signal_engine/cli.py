import sys
from pathlib import Path
from signal_engine.store import Store
from signal_engine.sources.github_releases import fetch_github_releases

def run_github_source(owner: str, repo: str, source_name: str, db_path: Path):
    store = Store(db_path)
    
    print(f"Fetching {owner}/{repo}...")
    items = fetch_github_releases(owner, repo, per_page=50)
    
    # Filter out drafts only (keep pre-releases - llama.cpp uses prereleases heavily)
    items = [i for i in items if not i['metadata'].get('draft')]
    
    print(f"Fetched {len(items)} releases, inserting into store...")
    inserted = store.upsert_items(source_name, items)
    total = store.count_items(source_name)
    
    print(f"\nResults:")
    print(f"  Items fetched: {len(items)}")
    print(f"  Items inserted this run: {inserted}")
    print(f"  Total items in store for {source_name}: {total}")
    
    # Show sample
    sample = store.get_items(source_name, limit=3)
    print("\nLatest items:")
    for id_, title, url, published in sample:
        print(f"  - {title[:80]}")
        print(f"    {url}")
    
    return inserted, total

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="data/signal.db", help="Path to SQLite DB")
    parser.add_argument("--source", default="llama-cpp-releases", help="Source name in PROFILE")
    args = parser.parse_args()
    
    db_path = Path(args.db)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Stage 1: One source - llama.cpp GitHub releases
    inserted, total = run_github_source(
        owner="ggml-org",
        repo="llama.cpp",
        source_name=args.source,
        db_path=db_path
    )
    
    # Prove deduplication by running again
    print("\n--- Running again to prove dedupe ---")
    store = Store(db_path)
    items = fetch_github_releases("ggml-org", "llama.cpp", per_page=50)
    items = [i for i in items if not i['metadata'].get('draft')]
    inserted_2 = store.upsert_items(args.source, items)
    total_2 = store.count_items(args.source)
    
    print(f"\nRe-run results:")
    print(f"  Items inserted on re-run: {inserted_2}")
    print(f"  Total items unchanged: {total_2 == total}")
    
    if inserted_2 == 0:
        print("\n✓ Dedup works: re-run added 0 items")
    else:
        print(f"\n⚠ Re-run added {inserted_2} new items")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())