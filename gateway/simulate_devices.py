"""
Simulate 3 edge devices sending SegmentRoot reports to the gateway.

Usage:
    python gateway/simulate_devices.py

Simulates:
- cam_001: Uses real video processing (if available)
- cam_002: Random generated hashes
- cam_003: Random generated hashes

Each device sends a report every 10 seconds.
"""

import asyncio
import hashlib
import random
import time
from datetime import datetime, timezone

import httpx


GATEWAY_URL = "http://localhost:8000/report"
DEVICES = ["cam_001", "cam_002", "cam_003"]


def generate_random_hash() -> str:
    """Generate a random SHA-256 hash."""
    random_data = f"{time.time()}_{random.random()}".encode()
    return hashlib.sha256(random_data).hexdigest()


def generate_semantic_summaries(device_id: str) -> list[str]:
    """Generate mock semantic summaries."""
    templates = [
        f"[{device_id}] Vehicle detected at intersection",
        f"[{device_id}] Pedestrian crossing detected",
        f"[{device_id}] Traffic light status: green",
        f"[{device_id}] No violations detected",
        f"[{device_id}] Normal traffic flow",
    ]
    return random.sample(templates, k=random.randint(1, 3))


async def send_device_report(client: httpx.AsyncClient, device_id: str):
    """Send a single device report to the gateway."""
    report = {
        "device_id": device_id,
        "segment_root": generate_random_hash(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "semantic_summaries": generate_semantic_summaries(device_id),
        "gop_count": random.randint(100, 200),
    }

    try:
        response = await client.post(GATEWAY_URL, json=report, timeout=5.0)
        if response.status_code == 200:
            print(f"✓ [{device_id}] Report sent successfully: {report['segment_root'][:16]}...")
        else:
            print(f"✗ [{device_id}] Failed: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"✗ [{device_id}] Error: {e}")


async def device_loop(device_id: str, interval: float = 10.0):
    """Continuously send reports for a single device."""
    async with httpx.AsyncClient() as client:
        while True:
            await send_device_report(client, device_id)
            await asyncio.sleep(interval)


async def main():
    """Run all device simulations concurrently."""
    print(f"Starting device simulation for {len(DEVICES)} devices...")
    print(f"Gateway URL: {GATEWAY_URL}")
    print(f"Report interval: 10 seconds")
    print("-" * 60)

    # Start all device loops concurrently
    tasks = [device_loop(device_id) for device_id in DEVICES]
    await asyncio.gather(*tasks)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nSimulation stopped by user.")
