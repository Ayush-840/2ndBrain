#!/usr/bin/env python3
"""Ingest wiki articles into the second-brain backend."""

import sys
from pathlib import Path

# Add the project root to the path
sys.path.insert(0, str(Path(__file__).parent))

from backend.pipeline import Pipeline

def main():
    vault_dir = Path("second-brain/wiki")
    if not vault_dir.exists():
        print(f"Error: {vault_dir} not found")
        sys.exit(1)

    print("Initializing pipeline...")
    pipeline = Pipeline()
    
    # Find all markdown files in the wiki
    md_files = list(vault_dir.rglob("*.md"))
    print(f"Found {len(md_files)} markdown files")
    
    # Ingest each file
    total_chunks = 0
    for i, md_file in enumerate(md_files, 1):
        print(f"[{i}/{len(md_files)}] Ingesting: {md_file.name}")
        try:
            result = pipeline.ingest_source(str(md_file), "markdown")
            chunks = result.get("num_chunks", 0)
            total_chunks += chunks
            print(f"  -> {chunks} chunks")
        except Exception as e:
            print(f"  -> Error: {e}")
            import traceback
            traceback.print_exc()
    
    print(f"\n=== Summary ===")
    print(f"Files processed: {len(md_files)}")
    print(f"Total chunks: {total_chunks}")
    print(f"Episodic store: {pipeline.store.count} chunks")
    print(f"BM25 index: {pipeline.bm25.count} documents")

if __name__ == "__main__":
    main()
