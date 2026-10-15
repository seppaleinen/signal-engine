import sqlite3
import json
from pathlib import Path
from typing import Iterable
from datetime import datetime

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    body TEXT,
    published_at TEXT,
    engagement INTEGER,
    metadata TEXT,
    filtered_by TEXT,
    decision TEXT,
    in_digest TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sources (
    source TEXT PRIMARY KEY,
    last_fetched_at TEXT,
    items_fetched INTEGER
);
"""

def init_db(db_path: str | Path) -> None:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()

class Store:
    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        init_db(self.db_path)
    
    def upsert_items(self, source: str, items: Iterable[dict]) -> int:
        if not items:
            return 0
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        inserted = 0
        now = datetime.utcnow().isoformat()
        for item in items:
            try:
                metadata_json = json.dumps(item.get('metadata', {}))
                cursor.execute("""
                    INSERT OR IGNORE INTO items 
                    (id, source, title, url, body, published_at, engagement, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    item['id'],
                    source,
                    item['title'],
                    item['url'],
                    item.get('body', ''),
                    item.get('published_at'),
                    item.get('engagement'),
                    metadata_json
                ))
                if cursor.rowcount > 0:
                    inserted += 1
            except Exception as e:
                print(f"Error inserting {item.get('id')}: {e}")
        
        # Update source tracking
        cursor.execute("""
            INSERT INTO sources (source, last_fetched_at, items_fetched)
            VALUES (?, ?, ?)
            ON CONFLICT(source) DO UPDATE SET 
                last_fetched_at = excluded.last_fetched_at,
                items_fetched = excluded.items_fetched
        """, (source, now, inserted))
        
        conn.commit()
        conn.close()
        return inserted
    
    def count_items(self, source: str | None = None) -> int:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        if source:
            cursor.execute("SELECT COUNT(*) FROM items WHERE source = ?", (source,))
        else:
            cursor.execute("SELECT COUNT(*) FROM items")
        count = cursor.fetchone()[0]
        conn.close()
        return count
    
    def get_items(self, source: str, limit: int = 10):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, title, url, published_at 
            FROM items 
            WHERE source = ? 
            ORDER BY published_at DESC 
            LIMIT ?
        """, (source, limit))
        rows = cursor.fetchall()
        conn.close()
        return rows