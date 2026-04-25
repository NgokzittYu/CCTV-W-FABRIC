#!/usr/bin/env python3
"""Recover missing batch files from event files."""

import json
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from config import SETTINGS

def recover_batches():
    """Scan event files and recreate missing batch files."""
    evidence_dir = Path(SETTINGS.evidence_dir)
    batches_dir = evidence_dir / "batches"

    # Get existing batch IDs
    existing_batches = set()
    if batches_dir.exists():
        for batch_file in batches_dir.rglob("batch_*.json"):
            batch_data = json.loads(batch_file.read_text(encoding="utf-8"))
            existing_batches.add(batch_data.get("batch_id"))

    print(f"Found {len(existing_batches)} existing batch files")

    # Scan all event files and group by batch_id
    print("Scanning event files...")
    batches = defaultdict(list)

    for event_file in evidence_dir.glob("event_*.json"):
        try:
            event_data = json.loads(event_file.read_text(encoding="utf-8"))
            merkle_info = event_data.get("_merkle")
            anchor_info = event_data.get("_anchor")

            if merkle_info and anchor_info:
                batch_id = merkle_info.get("batchId")
                if batch_id and batch_id not in existing_batches:
                    batches[batch_id].append({
                        "event_id": event_data.get("event_id"),
                        "evidence_hash": event_data.get("evidence_hash"),
                        "leaf_index": merkle_info.get("leafIndex", 0),
                        "merkle_info": merkle_info,
                        "anchor_info": anchor_info,
                    })
        except Exception as e:
            continue

    print(f"Found {len(batches)} missing batches in event files")

    # Recreate batch files
    recovered = 0
    for batch_id, events in batches.items():
        try:
            # Sort events by leaf index
            events.sort(key=lambda e: e["leaf_index"])

            # Get batch metadata from first event
            first_event = events[0]
            merkle_info = first_event["merkle_info"]
            anchor_info = first_event["anchor_info"]

            window_start = merkle_info.get("windowStart", 0)
            batch_date = datetime.fromtimestamp(window_start).strftime("%Y-%m-%d")
            batch_dir = batches_dir / batch_date
            batch_dir.mkdir(parents=True, exist_ok=True)

            batch_file = batch_dir / f"{batch_id}.json"

            batch_data = {
                "batch_id": batch_id,
                "camera_id": SETTINGS.camera_id,
                "merkle_root": merkle_info.get("merkleRoot", ""),
                "window_start": window_start,
                "window_end": merkle_info.get("windowEnd", 0),
                "tx_id": anchor_info.get("txId", ""),
                "block_number": anchor_info.get("blockNumber", 0),
                "timestamp": merkle_info.get("timestamp", 0),
                "event_count": len(events),
                "events": [
                    {
                        "event_id": e["event_id"],
                        "evidence_hash": e["evidence_hash"],
                        "leaf_index": e["leaf_index"],
                        "proof": e["merkle_info"].get("proof", []),
                    }
                    for e in events
                ],
            }

            batch_file.write_text(json.dumps(batch_data, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"✓ Recovered: {batch_id} (block #{anchor_info.get('blockNumber')}, {len(events)} events)")
            recovered += 1

        except Exception as e:
            print(f"✗ Failed to recover {batch_id}: {e}")

    print(f"\n{'='*60}")
    print(f"Recovery complete: {recovered} batches recovered")
    print(f"{'='*60}")

if __name__ == "__main__":
    recover_batches()
