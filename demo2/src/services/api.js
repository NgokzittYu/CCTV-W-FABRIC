/**
 * SecureLens API Client
 * Wraps all backend API calls to /api/video/*
 */

const API_BASE = 'http://localhost:8000';

/**
 * Upload video for evidence archiving.
 * @param {File} file - Video file
 * @param {string} deviceId - Device ID
 * @returns {Promise<Object>}
 */
export async function uploadVideo(file, deviceId = 'cctv-default-01') {
  const form = new FormData();
  form.append('file', file);
  form.append('device_id', deviceId);

  const res = await fetch(`${API_BASE}/api/video/upload`, {
    method: 'POST',
    body: form,
  });
  return res.json();
}

/**
 * List all archived videos.
 * @returns {Promise<{videos: Array}>}
 */
export async function listVideos() {
  const res = await fetch(`${API_BASE}/api/video/list`);
  return res.json();
}

/**
 * Get video certificate details.
 * @param {string} videoId
 * @returns {Promise<Object>}
 */
export async function getVideoCertificate(videoId) {
  const res = await fetch(`${API_BASE}/api/video/${videoId}/certificate`);
  return res.json();
}

/**
 * Verify an uploaded video against an original.
 * @param {File} file - Video file to verify
 * @param {string} originalVideoId - Original video ID
 * @returns {Promise<Object>}
 */
export async function verifyVideo(file, originalVideoId) {
  const form = new FormData();
  form.append('file', file);
  form.append('original_video_id', originalVideoId);

  const res = await fetch(`${API_BASE}/api/video/verify`, {
    method: 'POST',
    body: form,
  });
  return res.json();
}

/**
 * Get verification history.
 * @param {number} limit
 * @returns {Promise<{history: Array}>}
 */
export async function getVerifyHistory(limit = 50) {
  const res = await fetch(`${API_BASE}/api/video/verify/history?limit=${limit}`);
  return res.json();
}

/**
 * Get backend config.
 * @returns {Promise<Object>}
 */
export async function getConfig() {
  const res = await fetch(`${API_BASE}/api/config`);
  return res.json();
}
