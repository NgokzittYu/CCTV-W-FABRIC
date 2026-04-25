#!/usr/bin/env python3
"""Test script to verify the fixes."""

import json
from pathlib import Path

EVIDENCE_DIR = Path("evidences")

# Test 1: Check batch with missing event files
print("=" * 60)
print("Test 1: Checking batch with potentially missing events")
print("=" * 60)

batch_file = EVIDENCE_DIR / "batches/2026-03-04/batch_1772624214_1772624224_4ee045.json"
if batch_file.exists():
    batch_data = json.loads(batch_file.read_text(encoding="utf-8"))
    print(f"Batch ID: {batch_data.get('batch_id')}")
    print(f"Block Number: {batch_data.get('block_number')}")
    print(f"Event Count: {len(batch_data.get('events', []))}")
    print(f"\nChecking event files:")

    missing_count = 0
    for event in batch_data.get("events", [])[:5]:  # Check first 5
        event_id = event.get("event_id")
        event_file = EVIDENCE_DIR / f"{event_id}.json"
        exists = event_file.exists()
        status = "✓ EXISTS" if exists else "✗ MISSING"
        print(f"  {event_id}: {status}")
        if not exists:
            missing_count += 1

    print(f"\nMissing files: {missing_count}")
else:
    print("Batch file not found")

# Test 2: Check recent event files
print("\n" + "=" * 60)
print("Test 2: Checking recent event files")
print("=" * 60)

event_files = sorted(EVIDENCE_DIR.glob("event_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:3]
for ef in event_files:
    event_data = json.loads(ef.read_text(encoding="utf-8"))
    event_id = ef.stem
    top_class = event_data.get("top_class", "unknown")
    detections = len(event_data.get("detections", []))
    print(f"  {event_id}: type={top_class}, detections={detections}")

print("\n" + "=" * 60)
print("Fix Summary:")
print("=" * 60)
print("1. Modified /api/verify to query blockchain when local file missing")
print("2. Modified /api/batch to query blockchain for event details")
print("3. Added 'match' field to verify response for frontend compatibility")
print("4. Enhanced event type detection with fallback options")
print("\nPlease restart the web server to apply changes:")
print("  python web_app.py")
