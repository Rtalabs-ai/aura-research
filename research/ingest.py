# SPDX-License-Identifier: Apache-2.0
"""
Document ingestion module for Aura Research.

Wraps Aura Core's compile_directory() to ingest raw documents into .aura archives.
Supports incremental ingestion (only new/changed files) and watch mode.
"""

import json
import hashlib
import logging
import time
from pathlib import Path
from typing import Optional, Dict
from datetime import datetime

logger = logging.getLogger(__name__)


def _file_hash(filepath: Path) -> str:
    """Compute SHA-256 hash of a file for change detection."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def _load_manifest(state_dir: Path) -> Dict:
    """Load the ingestion manifest tracking what's been processed."""
    manifest_path = state_dir / "ingested.json"
    if manifest_path.exists():
        with open(manifest_path, "r") as f:
            return json.load(f)
    return {"files": {}, "last_ingest": None}


def _save_manifest(state_dir: Path, manifest: Dict):
    """Save the ingestion manifest."""
    state_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = state_dir / "ingested.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)


def ingest_documents(
    raw_dir: Path,
    output_path: Path,
    state_dir: Path,
    incremental: bool = True,
    show_progress: bool = True,
) -> dict:
    """
    Ingest raw documents into an .aura archive.

    Args:
        raw_dir: Directory containing raw source documents
        output_path: Path for the .aura output file
        state_dir: Path to .research/ state directory
        incremental: Only process new/changed files
        show_progress: Show progress bar

    Returns:
        Dict with ingestion stats
    """
    try:
        from aura.compiler import compile_directory
    except ImportError:
        print("❌ aura-core not installed. Run: pip install auralith-aura")
        raise

    if not raw_dir.exists():
        raise FileNotFoundError(f"Raw directory not found: {raw_dir}")

    manifest = _load_manifest(state_dir) if incremental else {"files": {}, "last_ingest": None}

    # Check for new/changed files
    current_files = {}
    new_or_changed = []
    for filepath in sorted(raw_dir.rglob("*")):
        if filepath.is_file() and not filepath.name.startswith("."):
            rel = str(filepath.relative_to(raw_dir))
            file_hash = _file_hash(filepath)
            current_files[rel] = file_hash
            if rel not in manifest["files"] or manifest["files"][rel] != file_hash:
                new_or_changed.append(rel)

    if incremental and not new_or_changed:
        print("✅ No new or changed files to ingest.")
        return {"new_files": 0, "total_files": len(current_files)}

    if new_or_changed:
        print(f"📥 Found {len(new_or_changed)} new/changed file(s)")
        for f in new_or_changed[:10]:
            print(f"   + {f}")
        if len(new_or_changed) > 10:
            print(f"   ... and {len(new_or_changed) - 10} more")

    # Full recompile (Aura Core compiles entire directory)
    print(f"\n🔥 Compiling: {raw_dir} → {output_path}")
    stats = compile_directory(
        input_dir=str(raw_dir),
        output_path=str(output_path),
        show_progress=show_progress,
    )

    # Update manifest
    manifest["files"] = current_files
    manifest["last_ingest"] = datetime.utcnow().isoformat() + "Z"
    _save_manifest(state_dir, manifest)

    result = {
        "new_files": len(new_or_changed),
        "total_files": stats.processed_files,
        "total_words": stats.total_tokens,
        "failed": stats.failed_files,
    }

    print(f"✅ Ingested {stats.processed_files} files ({stats.total_tokens:,} words)")
    if stats.failed_files:
        print(f"   ⚠️  {stats.failed_files} files failed")

    return result


def watch_and_ingest(
    raw_dir: Path,
    output_path: Path,
    state_dir: Path,
    interval: int = 5,
):
    """
    Watch the raw directory for changes and re-ingest automatically.

    Args:
        raw_dir: Directory to watch
        output_path: Path for the .aura output file
        state_dir: State directory
        interval: Check interval in seconds
    """
    try:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler
    except ImportError:
        # Fallback: simple polling
        print("📡 Watch mode (polling every {}s) — install watchdog for better performance".format(interval))
        print("   Press Ctrl+C to stop\n")
        try:
            while True:
                ingest_documents(raw_dir, output_path, state_dir, incremental=True, show_progress=False)
                time.sleep(interval)
        except KeyboardInterrupt:
            print("\n👋 Watch mode stopped.")
        return

    class IngestHandler(FileSystemEventHandler):
        def __init__(self):
            self._pending = False

        def on_any_event(self, event):
            if not event.is_directory:
                self._pending = True

    handler = IngestHandler()
    observer = Observer()
    observer.schedule(handler, str(raw_dir), recursive=True)
    observer.start()

    print(f"📡 Watching {raw_dir} for changes (Ctrl+C to stop)")
    try:
        while True:
            if handler._pending:
                handler._pending = False
                time.sleep(1)  # Brief debounce
                print(f"\n🔄 Changes detected — re-ingesting...")
                ingest_documents(raw_dir, output_path, state_dir, incremental=True, show_progress=False)
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n👋 Watch mode stopped.")
    finally:
        observer.stop()
        observer.join()
