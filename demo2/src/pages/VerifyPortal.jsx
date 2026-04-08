import { useState, useEffect, useCallback } from 'react';
import {
  ShieldCheck, Upload, FileText, History, Search,
  Video, RefreshCw, Clock, AlertTriangle, CheckCircle2
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { listVideos, verifyVideo, getVerifyHistory } from '../services/api';
import RiskGauge from '../components/RiskGauge';


export default function VerifyPortal({ activeTab }) {
  switch (activeTab) {
    case 'verify':  return <VerifyTab />;
    case 'report':  return <ReportTab />;
    case 'history': return <HistoryTab />;
    default:        return <VerifyTab />;
  }
}


// ═══════════════════════════════════════════════════════════════
// Tab 1: 证据验真
// ═══════════════════════════════════════════════════════════════
function VerifyTab() {
  const [videos, setVideos] = useState([]);
  const [selectedVideoId, setSelectedVideoId] = useState('');
  const [verifying, setVerifying] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    listVideos()
      .then((d) => setVideos(d.videos || []))
      .catch(() => {});
  }, []);

  const handleVerify = async (e) => {
    const file = e.target.files?.[0];
    if (!file || !selectedVideoId) return;

    setVerifying(true);
    setResult(null);
    setError('');

    try {
      const data = await verifyVideo(file, selectedVideoId);
      if (data.error) {
        setError(data.error);
      } else {
        setResult(data);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setVerifying(false);
    }
  };

  return (
    <div className="dashboard-content">
      <div className="dashboard-header">
        <h2><ShieldCheck size={22} /> 证据验真</h2>
        <p className="text-muted">上传待验视频，与链上存证进行逐 GOP 三态比对</p>
      </div>

      {/* Step 1: Select original */}
      <div className="verify-step glass-card" style={{ marginTop: 20 }}>
        <div className="verify-step-num">1</div>
        <div className="verify-step-body">
          <h4>选择原始存证</h4>
          <p className="text-muted" style={{ fontSize: '0.8rem', marginBottom: 12 }}>
            选择要比对的原始存证视频
          </p>
          {videos.length === 0 ? (
            <p className="text-muted" style={{ fontSize: '0.8rem' }}>
              暂无存证视频。请先通过管理方上传存证后再进行验真。
            </p>
          ) : (
            <select
              className="verify-select"
              value={selectedVideoId}
              onChange={(e) => setSelectedVideoId(e.target.value)}
            >
              <option value="">-- 请选择 --</option>
              {videos.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.filename} ({v.gop_count} GOPs) — {v.id}
                </option>
              ))}
            </select>
          )}
        </div>
      </div>

      {/* Step 2: Upload verify video */}
      <div className="verify-step glass-card">
        <div className="verify-step-num">2</div>
        <div className="verify-step-body">
          <h4>上传待验视频</h4>
          <p className="text-muted" style={{ fontSize: '0.8rem', marginBottom: 12 }}>
            上传可能经过压缩、转码或篡改的视频文件
          </p>
          <label
            className={`btn ${selectedVideoId ? 'btn-primary' : 'btn-secondary'}`}
            style={{ cursor: !selectedVideoId || verifying ? 'not-allowed' : 'pointer', opacity: selectedVideoId ? 1 : 0.5 }}
          >
            <Upload size={14} /> {verifying ? '验真中...' : '上传并验真'}
            <input
              type="file"
              accept="video/*"
              hidden
              onChange={handleVerify}
              disabled={!selectedVideoId || verifying}
            />
          </label>
        </div>
      </div>

      {/* Error */}
      {error && (
        <motion.div
          className="glass-card"
          style={{ padding: 16, color: 'var(--accent-red)', marginTop: 16 }}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
        >
          <AlertTriangle size={14} /> {error}
        </motion.div>
      )}

      {/* Result */}
      <AnimatePresence>
        {result && (
          <motion.div
            className="verify-result glass-card"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
          >
            <VerifyResultPanel data={result} />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}


// ═══════════════════════════════════════════════════════════════
// Verify Result Panel (shared)
// ═══════════════════════════════════════════════════════════════
function VerifyResultPanel({ data }) {
  const statusBadgeClass = {
    INTACT: 'badge-intact',
    RE_ENCODED: 'badge-re-encoded',
    TAMPERED: 'badge-tampered',
  };

  return (
    <div className="verify-result-content">
      <div className="verify-result-header">
        <RiskGauge status={data.overall_status} risk={data.overall_risk} size={180} />
        <div className="verify-result-summary">
          <h3>
            验真结果：
            <span className={`badge ${statusBadgeClass[data.overall_status] || ''}`} style={{ marginLeft: 8 }}>
              {data.overall_status}
            </span>
          </h3>
          <p className="text-muted" style={{ fontSize: '0.85rem', marginTop: 8 }}>
            原始 GOP: {data.original_gop_count} 段 · 待验 GOP: {data.current_gop_count} 段
          </p>
          <p className="text-muted" style={{ fontSize: '0.85rem' }}>
            综合风险: {(data.overall_risk * 100).toFixed(2)}%
          </p>
        </div>
      </div>

      {/* GOP-level results */}
      {data.gop_results && data.gop_results.length > 0 && (
        <div className="gop-results-grid">
          <h4 style={{ marginBottom: 12, fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
            逐 GOP 比对结果
          </h4>
          <div className="gop-results-list">
            {data.gop_results.map((gop, i) => (
              <div
                key={i}
                className={`gop-result-item gop-${gop.status.toLowerCase()}`}
                title={`GOP #${gop.gop_index}: ${gop.detail}`}
              >
                <span className="gop-result-idx">#{gop.gop_index}</span>
                <div className="gop-result-bar">
                  <div
                    className="gop-result-fill"
                    style={{ width: `${Math.max(gop.risk * 100, 2)}%` }}
                  />
                </div>
                <span className="gop-result-risk">{(gop.risk * 100).toFixed(1)}%</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}


// ═══════════════════════════════════════════════════════════════
// Tab 2: 验真报告 (displays latest result)
// ═══════════════════════════════════════════════════════════════
function ReportTab() {
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getVerifyHistory(1)
      .then((d) => setHistory(d.history || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const latest = history[0];

  return (
    <div className="dashboard-content">
      <div className="dashboard-header">
        <h2><FileText size={22} /> 验真报告</h2>
        <p className="text-muted">最近一次验真的详细报告</p>
      </div>

      {loading ? (
        <div className="loading-placeholder">加载中...</div>
      ) : !latest ? (
        <div className="empty-state glass-card">
          <FileText size={32} style={{ color: 'var(--text-muted)' }} />
          <p>暂无验真记录</p>
          <p className="text-muted" style={{ fontSize: '0.8rem' }}>
            前往「证据验真」进行第一次验真后查看报告
          </p>
        </div>
      ) : (
        <div className="verify-result glass-card" style={{ marginTop: 20 }}>
          <div style={{ marginBottom: 16 }}>
            <p className="text-muted" style={{ fontSize: '0.8rem' }}>
              验真 ID: <span className="mono">{latest.id}</span>
            </p>
            <p className="text-muted" style={{ fontSize: '0.8rem' }}>
              原始视频: <span className="mono">{latest.original_video_id}</span>
            </p>
            <p className="text-muted" style={{ fontSize: '0.8rem' }}>
              上传文件: {latest.uploaded_filename}
            </p>
            <p className="text-muted" style={{ fontSize: '0.8rem' }}>
              时间: {latest.created_at ? new Date(latest.created_at * 1000).toLocaleString('zh-CN') : '—'}
            </p>
          </div>
          <VerifyResultPanel
            data={{
              overall_status: latest.overall_status,
              overall_risk: latest.overall_risk,
              original_gop_count: latest.gop_results?.length || 0,
              current_gop_count: latest.gop_results?.length || 0,
              gop_results: latest.gop_results || [],
            }}
          />
        </div>
      )}
    </div>
  );
}


// ═══════════════════════════════════════════════════════════════
// Tab 3: 历史记录
// ═══════════════════════════════════════════════════════════════
function HistoryTab() {
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(() => {
    setLoading(true);
    getVerifyHistory(50)
      .then((d) => setHistory(d.history || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const statusIcon = {
    INTACT: <CheckCircle2 size={14} style={{ color: 'var(--accent-green)' }} />,
    RE_ENCODED: <AlertTriangle size={14} style={{ color: 'var(--accent-amber)' }} />,
    TAMPERED: <AlertTriangle size={14} style={{ color: 'var(--accent-red)' }} />,
  };

  const statusBadgeClass = {
    INTACT: 'badge-intact',
    RE_ENCODED: 'badge-re-encoded',
    TAMPERED: 'badge-tampered',
  };

  return (
    <div className="dashboard-content">
      <div className="dashboard-header">
        <h2><History size={22} /> 历史记录</h2>
        <div style={{ display: 'flex', gap: 12 }}>
          <button className="btn btn-ghost btn-sm" onClick={refresh}>
            <RefreshCw size={14} /> 刷新
          </button>
        </div>
      </div>

      {loading ? (
        <div className="loading-placeholder">加载中...</div>
      ) : history.length === 0 ? (
        <div className="empty-state glass-card">
          <History size={32} style={{ color: 'var(--text-muted)' }} />
          <p>暂无验真记录</p>
        </div>
      ) : (
        <div className="history-list" style={{ marginTop: 16 }}>
          {history.map((rec, i) => (
            <motion.div
              key={rec.id}
              className="glass-card history-item"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.05 }}
            >
              <div className="history-item-icon">
                {statusIcon[rec.overall_status]}
              </div>
              <div className="history-item-body">
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                  <span className="mono" style={{ fontSize: '0.75rem' }}>{rec.id}</span>
                  <span className={`badge ${statusBadgeClass[rec.overall_status] || ''}`}>
                    {rec.overall_status}
                  </span>
                </div>
                <div className="text-muted" style={{ fontSize: '0.75rem' }}>
                  原始: {rec.original_video_id} · 文件: {rec.uploaded_filename}
                </div>
                <div className="text-muted" style={{ fontSize: '0.7rem' }}>
                  风险: {(rec.overall_risk * 100).toFixed(2)}% ·
                  GOPs: {rec.gop_results?.length || 0} ·
                  <Clock size={10} style={{ marginLeft: 4 }} />
                  {' '}{rec.created_at ? new Date(rec.created_at * 1000).toLocaleString('zh-CN') : '—'}
                </div>
              </div>
            </motion.div>
          ))}
        </div>
      )}
    </div>
  );
}
