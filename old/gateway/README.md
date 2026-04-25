# Gateway Service - Multi-Device Epoch Aggregation

## Overview

The gateway service aggregates SegmentRoots from multiple edge devices into epoch-level Merkle trees, anchoring them to the blockchain every 30 seconds.

## Architecture

```
Edge Devices (cam_001, cam_002, cam_003)
    ↓ POST /report (every 10s)
Gateway Service
    ↓ Aggregates reports into epochs (every 30s)
EpochMerkleTree (device SegmentRoots as leaves)
    ↓ Anchors EpochRoot to blockchain
Fabric Blockchain
```

## Components

### 1. EpochMerkleTree (`services/merkle_utils.py`)
- Aggregates multiple device SegmentRoots into a single EpochRoot
- Each device contributes one leaf per epoch
- Supports proof generation and verification
- Serializable to JSON for persistence

### 2. GatewayService (`services/gateway_service.py`)
- Manages epoch lifecycle (collect → build → anchor → store)
- SQLite database for historical data
- Automatic deduplication (last-write-wins per device)
- Thread-safe with asyncio.Lock

### 3. Web API Routes (`web_app.py`)
- `POST /report` - Receive device reports
- `GET /epochs` - List recent epochs
- `GET /epoch/{epoch_id}` - Get epoch details
- `GET /proof/{epoch_id}/{device_id}` - Get Merkle proof

### 4. Device Simulator (`gateway/simulate_devices.py`)
- Simulates 3 edge devices sending reports
- Random hash generation for testing
- Configurable report interval

## Installation

```bash
pip install apscheduler httpx
```

## Usage

### Start the Gateway Server

```bash
python web_app.py
```

The server will:
- Start on `http://localhost:8000`
- Initialize the gateway service with SQLite database at `data/gateway.db`
- Schedule epoch flushing every 30 seconds

### Run Device Simulation

In a separate terminal:

```bash
python gateway/simulate_devices.py
```

This will simulate 3 devices (`cam_001`, `cam_002`, `cam_003`) sending reports every 10 seconds.

### Query Epochs

List recent epochs:
```bash
curl http://localhost:8000/epochs
```

Get epoch details:
```bash
curl http://localhost:8000/epoch/epoch_20260316_142500
```

Get device proof:
```bash
curl http://localhost:8000/proof/epoch_20260316_142500/cam_001
```

### Manual Device Report

```bash
curl -X POST http://localhost:8000/report \
  -H "Content-Type: application/json" \
  -d '{
    "device_id": "cam_001",
    "segment_root": "a3f8c1d2e5b6...",
    "timestamp": "2026-03-16T14:25:00Z",
    "semantic_summaries": ["Vehicle detected", "Normal traffic"],
    "gop_count": 150
  }'
```

## Database Schema

### epochs table
- `epoch_id` (PRIMARY KEY) - Unique epoch identifier
- `epoch_root` - Merkle root of all device SegmentRoots
- `device_count` - Number of devices in this epoch
- `tx_id` - Blockchain transaction ID
- `created_at` - Timestamp
- `tree_json` - Serialized EpochMerkleTree

### device_reports table
- `id` (PRIMARY KEY) - Auto-increment
- `epoch_id` - Foreign key to epochs
- `device_id` - Device identifier
- `segment_root` - Device's SegmentRoot hash
- `timestamp` - Report timestamp
- `gop_count` - Number of GOPs in segment
- `semantic_summaries` - JSON array of summaries

## Testing

Run unit tests:
```bash
pytest tests/test_epoch_merkle.py -v
```

All 11 tests should pass:
- Basic tree construction
- Proof generation and verification
- Serialization/deserialization
- Deduplication logic
- Error handling
- Deterministic ordering
- Large tree performance

## Design Decisions

1. **30-second epoch window** - Balances blockchain cost with freshness
2. **Last-write-wins deduplication** - Simple conflict resolution for duplicate reports
3. **Asyncio.Lock** - Protects concurrent access between API handlers and scheduler
4. **Thread pool for blocking I/O** - SQLite and Fabric calls wrapped in `asyncio.to_thread()`
5. **Deterministic ordering** - Devices sorted by device_id for reproducible roots
6. **Separate from MerkleBatchManager** - Gateway operates at device-segment level, MerkleBatchManager at event level

## Integration with Existing System

The gateway service is **additive** and does not modify existing functionality:
- `MerkleBatchManager` continues handling event-level batching
- `HierarchicalMerkleTree` continues handling within-device GOP aggregation
- `EpochMerkleTree` adds cross-device segment aggregation

## Troubleshooting

**Scheduler error on import:**
- Fixed by moving scheduler initialization to `@app.on_event("startup")`
- Scheduler requires running event loop

**Database locked:**
- Ensure only one gateway instance is running
- Check `data/gateway.db-journal` for stale locks

**Missing reports:**
- Check device simulator is running
- Verify network connectivity to gateway
- Check gateway logs for errors

## Future Enhancements

- Authentication for device reports
- Rate limiting per device
- Monitoring/alerting for missing devices
- Database connection pooling
- Graceful shutdown handling for pending reports
- Web UI for epoch visualization
