/**
 * SecureLens API Client
 * Connects demo2 frontend to the FastAPI backend (server.py)
 *
 * Updated: Phase 1-4
 * - getSystemHealth() now calls real /api/health endpoint
 * - getDevices() now calls real /api/devices endpoint
 * - Added IPFS, GOP verify, anchor stats, verification stats APIs
 */

const DIRECT_API_BASE = 'http://127.0.0.1:8000';
const DIRECT_WS_BASE = 'ws://127.0.0.1:8000';
const API_BASE = import.meta.env.VITE_API_BASE || '';
const WS_BASE = import.meta.env.VITE_WS_BASE || '';

function unique(values) {
  return [...new Set(values.filter(Boolean))];
}

function getApiBases() {
  return unique([
    API_BASE,
    '',
    DIRECT_API_BASE,
    'http://localhost:8000',
  ]);
}

export function buildApiUrl(path) {
  if (!path) return '';
  if (/^https?:\/\//.test(path)) return path;
  return `${API_BASE || ''}${path}`;
}

// ── Helpers ──────────────────────────────────────────────────────

async function get(path) {
  let lastError = null;

  for (const base of getApiBases()) {
    try {
      const res = await fetch(`${base}${path}`);
      if (!res.ok) {
        let message = `API ${res.status}: ${res.statusText}`;
        try {
          const data = await res.json();
          message = data?.error || data?.message || message;
        } catch {}
        throw new Error(message);
      }
      return res.json();
    } catch (error) {
      lastError = error;
    }
  }

  throw new Error(`GET ${path} failed: ${lastError?.message || 'unknown error'}`);
}

async function post(path, body) {
  let lastError = null;

  for (const base of getApiBases()) {
    try {
      const res = await fetch(`${base}${path}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        let message = `API ${res.status}: ${res.statusText}`;
        try {
          const data = await res.json();
          message = data?.error || data?.message || message;
        } catch {}
        throw new Error(message);
      }
      return res.json();
    } catch (error) {
      lastError = error;
    }
  }

  throw new Error(`POST ${path} failed: ${lastError?.message || 'unknown error'}`);
}

async function postForm(path, formData) {
  let lastError = null;

  for (const base of getApiBases()) {
    try {
      const res = await fetch(`${base}${path}`, {
        method: 'POST',
        body: formData,
      });
      if (!res.ok) {
        let message = `API ${res.status}: ${res.statusText}`;
        try {
          const data = await res.json();
          message = data?.error || data?.message || message;
        } catch {}
        throw new Error(message);
      }
      return res.json();
    } catch (error) {
      lastError = error;
    }
  }

  throw new Error(`POST ${path} failed: ${lastError?.message || 'unknown error'}`);
}

// ── System Health (Phase 1.1 — real backend endpoint) ────────────

/** Real health check — probes Fabric, IPFS, Gateway, Detection, GOP Anchor */
export async function getSystemHealth() {
  return get('/api/health');
}

/** IPFS node + cluster stats */
export async function getIpfsStats() {
  return get('/api/ipfs/stats');
}

/** Real device list from Gateway DB + local detection status */
export async function getDevices() {
  return get('/api/devices');
}

/** Fabric configuration */
export function getConfig() {
  return get('/api/config');
}

// ── Evidence / Blockchain Ledger ─────────────────────────────────

/** Recent blockchain batches */
export function getRecentBlocks(limit = 20) {
  return get(`/api/ledger/recent?limit=${limit}&_=${Date.now()}`);
}

/** Batch detail with enriched events */
export function getBatchDetails(batchId) {
  return get(`/api/batch/${batchId}`);
}

/** Query block by block number, batch id, or tx id */
export function queryLedger(q) {
  return get(`/api/ledger/query?q=${encodeURIComponent(q)}`);
}

/** Verify single event via Merkle proof */
export function verifyEvidence(eventId) {
  return post(`/api/verify/${eventId}`, {});
}

/** Event history from blockchain */
export function getEventHistory(eventId) {
  return get(`/api/history/${eventId}`);
}

// ── Gateway Epochs ───────────────────────────────────────────────

/** List recent gateway epochs */
export function listEpochs(limit = 20) {
  return get(`/epochs?limit=${limit}`);
}

/** Epoch aggregation detail */
export function getEpochDetails(epochId) {
  return get(`/epoch/${epochId}`);
}

/** Merkle proof for a device in an epoch */
export function getDeviceProof(epochId, deviceId) {
  return get(`/proof/${epochId}/${deviceId}`);
}

// ── Audit ────────────────────────────────────────────────────────

/** Export audit trail for a batch */
export function exportAuditTrail(batchId) {
  return get(`/api/audit/export/${batchId}`);
}

/** Verify audit report signature via chaincode */
export function verifyAuditReport(data) {
  return post('/api/audit/verify', data);
}

// ── Workorders ───────────────────────────────────────────────────

/** Create rectification workorder */
export function createWorkorder(data) {
  return post('/api/workorder/create', data);
}

/** Get workorder by ID */
export function getWorkorder(orderId) {
  return get(`/api/workorder/${orderId}`);
}

/** Submit rectification proof */
export function submitRectification(data) {
  return post('/api/workorder/submit', data);
}

/** Confirm or reject rectification */
export function confirmRectification(data) {
  return post('/api/workorder/confirm', data);
}

/** Query overdue workorders */
export function getOverdueWorkorders(org = null, page = 1, limit = 20) {
  let url = `/api/workorder/overdue?page=${page}&limit=${limit}`;
  if (org) url += `&org=${org}`;
  return get(url);
}

// ── WebSocket & Video Stream ─────────────────────────────────────

/** Create WebSocket for real-time detection events + tamper alerts */
export function createEventSocket(onMessage, onError) {
  const wsUrl = WS_BASE || DIRECT_WS_BASE;
  const ws = new WebSocket(`${wsUrl}/ws`);
  ws.onmessage = (e) => {
    try { onMessage(JSON.parse(e.data)); }
    catch { onMessage(e.data); }
  };
  ws.onerror = onError || (() => {});
  return ws;
}

/** MJPEG video feed URL (YOLO annotated) */
export function getVideoFeedURL(streamType = 'ann') {
  return `${API_BASE || DIRECT_API_BASE}/video_feed/${streamType}`;
}

// ── Video Evidence ──────────────────────────────────────────────

/** Upload video for GOP split + IPFS upload + Fabric anchor */
export function uploadVideo(file, deviceId = 'cctv-default-01') {
  const fd = new FormData();
  fd.append('file', file);
  fd.append('device_id', deviceId);
  return postForm('/api/video/upload', fd);
}

/** List all archived videos */
export function listVideos() {
  return get('/api/video/list');
}

/** Get video evidence certificate (with IPFS CIDs) */
export function getVideoCertificate(videoId) {
  return get(`/api/video/${videoId}/certificate`);
}

/** Verify uploaded video against original */
export function verifyVideo(file, originalVideoId) {
  const fd = new FormData();
  fd.append('file', file);
  fd.append('original_video_id', originalVideoId);
  return postForm('/api/video/verify', fd);
}

/** Verify a SecureLens-exported replay sample */
export function verifyExportedSample(file) {
  const fd = new FormData();
  fd.append('file', file);
  return postForm('/api/video/verify/export', fd);
}

/** Generate a tampered SecureLens-exported replay sample */
export function generateTamperedExportSample(file) {
  const fd = new FormData();
  fd.append('file', file);
  return postForm('/api/video/tamper/export', fd);
}

/** Get verification history */
export function getVerifyHistory(limit = 50) {
  return get(`/api/video/verify/history?limit=${limit}`);
}

// ── IPFS (Phase 1.2) ───────────────────────────────────────────

/** IPFS node statistics */
export function getIPFSStats() {
  return get('/api/ipfs/stats');
}

/** List GOPs stored in IPFS */
export function listIPFSGops(deviceId = '', start = 0, end = 0) {
  let url = `/api/ipfs/gops?device_id=${deviceId}&start=${start}&end=${end}`;
  return get(url);
}

/** Build replay playlist URL from wall-clock local time in a declared timezone */
export function getReplayPlaylistURL({ deviceId, startLocal, endLocal, timezone = 'Asia/Shanghai' }) {
  const params = new URLSearchParams({
    device_id: deviceId,
    start_local: startLocal,
    end_local: endLocal,
    timezone,
  });
  return buildApiUrl(`/api/ipfs/replay/playlist.m3u8?${params.toString()}`);
}

/** Download replay as a verification TS sample */
export function getReplayDownloadTsURL({ deviceId, startLocal, endLocal, timezone = 'Asia/Shanghai' }) {
  const params = new URLSearchParams({
    device_id: deviceId,
    start_local: startLocal,
    end_local: endLocal,
    timezone,
  });
  return buildApiUrl(`/api/ipfs/replay/download.ts?${params.toString()}`);
}

/** Download replay export manifest JSON */
export function getReplayDownloadJsonURL({ deviceId, startLocal, endLocal, timezone = 'Asia/Shanghai' }) {
  const params = new URLSearchParams({
    device_id: deviceId,
    start_local: startLocal,
    end_local: endLocal,
    timezone,
  });
  return buildApiUrl(`/api/ipfs/replay/download.json?${params.toString()}`);
}

// ── GOP Verification (Phase 1.3) ────────────────────────────────

/** End-to-end GOP verification: IPFS → SHA-256 → Fabric */
export function verifyGOP(deviceId, epochId, gopIndex) {
  return post('/api/gop/verify', { device_id: deviceId, epoch_id: epochId, gop_index: gopIndex });
}

// ── EIS/MAB Anchor Stats (Phase 4) ─────────────────────────────

/** EIS + MAB real-time anchor status */
export function getAnchorStats() {
  return get('/api/anchor/stats');
}

// ── Verification Stats (Phase 2.3) ─────────────────────────────

/** Verification statistics: total, status breakdown, integrity rate */
export function getVerificationStats() {
  return get('/api/stats/verification');
}
