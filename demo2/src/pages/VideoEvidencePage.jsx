import { useState, useEffect, useCallback, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Upload, FileVideo, ShieldCheck, History, Loader2, AlertTriangle, CheckCircle2, ChevronDown, PlayCircle, CalendarClock, RadioTower, ExternalLink, Download } from 'lucide-react';
import { uploadVideo, listVideos, getVideoCertificate, verifyExportedSample, getVerifyHistory, getDevices, getReplayPlaylistURL, generateTamperedExportSample, buildApiUrl } from '../services/api';
import VideoCard from '../components/VideoCard';
import CertificateCard from '../components/CertificateCard';
import RiskGauge from '../components/RiskGauge';
import GopResultsTable from '../components/GopResultsTable';
import HlsPlayer from '../components/HlsPlayer';
import { pickDefaultDeviceId } from '../constants/cameras';

const TABS = [
  { id: 'archive', label: '证据归档', icon: FileVideo },
  { id: 'verify',  label: '完整性验证', icon: ShieldCheck },
  { id: 'history', label: '验证历史', icon: History },
  { id: 'tamper',  label: '一键篡改', icon: AlertTriangle },
];

const REPLAY_TIMEZONE = 'Asia/Shanghai';
const EXPORT_SAMPLE_RE = /^sl__(?<device>[A-Za-z0-9_-]+)__(?<start>\d{8}T\d{6}\+\d{4})__(?<end>\d{8}T\d{6}\+\d{4})__g(?<gops>\d+)__gap(?<gap>[01])(?:\.[A-Za-z0-9]+)?$/;

function formatAsiaShanghaiDateTimeLocal(date = new Date()) {
  const formatter = new Intl.DateTimeFormat('sv-SE', {
    timeZone: REPLAY_TIMEZONE,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  });
  const parts = Object.fromEntries(
    formatter.formatToParts(date).map((part) => [part.type, part.value]),
  );
  return `${parts.year}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}:${parts.second}`;
}

function formatReplayRangeLabel(startLocal, endLocal) {
  if (!startLocal || !endLocal) return '';
  return `${startLocal.replace('T', ' ')} 至 ${endLocal.replace('T', ' ')}`;
}

function formatVerifyTimestamp(ts) {
  if (!ts) return '—';
  return new Date(ts * 1000).toLocaleString('zh-CN', { hour12: false });
}

function parseExportedSampleFilename(filename) {
  const match = filename?.match(EXPORT_SAMPLE_RE);
  if (!match?.groups) {
    return null;
  }

  const parseOffsetDate = (value) => {
    const normalized = value.replace(/^(\d{8})T(\d{6})([+-]\d{4})$/, '$1T$2$3');
    const iso = normalized.replace(/^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})([+-]\d{2})(\d{2})$/, '$1-$2-$3T$4:$5:$6$7:$8');
    const date = new Date(iso);
    return Number.isNaN(date.getTime()) ? null : Math.floor(date.getTime() / 1000);
  };

  const startTime = parseOffsetDate(match.groups.start);
  const endTime = parseOffsetDate(match.groups.end);
  if (!startTime || !endTime) return null;

  return {
    deviceId: match.groups.device,
    actualStartTime: startTime,
    actualEndTime: endTime,
    expectedGopCount: Number(match.groups.gops || 0),
    gapFlag: Number(match.groups.gap || 0),
    filename,
  };
}

export default function VideoEvidencePage({ role }) {
  const [tab, setTab] = useState('archive');

  return (
    <div className="main-content video-evidence-shell">
      <div className="video-evidence-tabs" role="tablist" aria-label="视频证据功能导航">
        {TABS.map((t) => {
          const Icon = t.icon;
          const active = tab === t.id;
          return (
            <button
              key={t.id}
              type="button"
              role="tab"
              aria-selected={active}
              className={`video-evidence-tab${active ? ' is-active' : ''}`}
              onClick={() => setTab(t.id)}
            >
              <Icon size={16} /> {t.label}
            </button>
          );
        })}
      </div>

      <AnimatePresence mode="wait" initial={false}>
        <motion.div
          key={tab}
          className="video-evidence-content"
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -6 }}
          transition={{ duration: 0.15 }}
        >
          {tab === 'archive' && <ArchiveTab role={role} />}
          {tab === 'verify'  && <VerifyTab />}
          {tab === 'history' && <HistoryTab />}
          {tab === 'tamper' && <TamperTab />}
        </motion.div>
      </AnimatePresence>
    </div>
  );
}

/* ── Archive Tab ── */
function ArchiveTab({ role }) {
  const [videos, setVideos] = useState([]);
  const [devices, setDevices] = useState([]);
  const [certData, setCertData] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState(null);
  const [replayDeviceId, setReplayDeviceId] = useState('');
  const [replayStartLocal, setReplayStartLocal] = useState(() => {
    const end = new Date();
    return formatAsiaShanghaiDateTimeLocal(new Date(end.getTime() - 5 * 60 * 1000));
  });
  const [replayEndLocal, setReplayEndLocal] = useState(() => formatAsiaShanghaiDateTimeLocal(new Date()));
  const [replayUrl, setReplayUrl] = useState('');
  const [replayError, setReplayError] = useState('');
  const [replayLoading, setReplayLoading] = useState(false);
  const [replaySummary, setReplaySummary] = useState(null);
  const fileRef = useRef(null);

  const load = useCallback(async () => {
    try {
      const [videoRes, deviceRes] = await Promise.allSettled([listVideos(), getDevices()]);
      const nextVideos = videoRes.status === 'fulfilled' ? (videoRes.value.videos || []) : [];
      const deviceOptions = new Map();
      const displayHints = new Map();

      if (deviceRes.status === 'fulfilled') {
        for (const device of deviceRes.value.devices || []) {
          if (!device?.device_id) continue;
          displayHints.set(device.device_id, device.label || device.device_id);
          deviceOptions.set(device.device_id, {
            device_id: device.device_id,
            label: device.label || device.device_id,
          });
        }
      }

      for (const video of nextVideos) {
        if (!video?.device_id) continue;
        deviceOptions.set(video.device_id, {
          device_id: video.device_id,
          label: displayHints.get(video.device_id) || video.device_id,
        });
      }

      const nextDevices = [...deviceOptions.values()];
      setVideos(nextVideos);
      setDevices(nextDevices);
      setReplayDeviceId((current) => current || pickDefaultDeviceId(nextDevices));
    } catch {}
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true); setUploadResult(null);
    try {
      const res = await uploadVideo(file);
      setUploadResult(res);
      load();
      // Show certificate for newly uploaded video
      if (res.video_id) {
        try { const cert = await getVideoCertificate(res.video_id); setCertData(cert); } catch {}
      }
    } catch (err) {
      setUploadResult({ error: err.message });
    } finally { setUploading(false); if (fileRef.current) fileRef.current.value = ''; }
  };

  const handleViewCert = async (videoId) => {
    try { const cert = await getVideoCertificate(videoId); setCertData(cert); } catch {}
  };

  const handleReplayGenerate = async () => {
    if (!replayDeviceId || !replayStartLocal || !replayEndLocal) {
      setReplayError('请先选择探头并填写完整的东八区起止时间。');
      return;
    }

    setReplayLoading(true);
    setReplayError('');
    setReplayUrl('');
    try {
      const nextUrl = getReplayPlaylistURL({
        deviceId: replayDeviceId,
        startLocal: replayStartLocal,
        endLocal: replayEndLocal,
        timezone: REPLAY_TIMEZONE,
      });
      const res = await fetch(nextUrl);
      if (!res.ok) {
        let message = '回放生成失败';
        const contentType = res.headers.get('content-type') || '';
        if (contentType.includes('application/json')) {
          const data = await res.json();
          message = data.error || message;
        } else {
          message = await res.text() || message;
        }
        throw new Error(message);
      }
      setReplayUrl(nextUrl);
      setReplaySummary({
        deviceId: replayDeviceId,
        rangeLabel: formatReplayRangeLabel(replayStartLocal, replayEndLocal),
      });
    } catch (err) {
      setReplayError(err.message);
    } finally {
      setReplayLoading(false);
    }
  };

  return (
    <>
      {/* Upload zone (admin only) */}
      {role === 'admin' && (
        <label style={{
          display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: '12px',
          padding: '40px', marginBottom: '32px', border: '2px dashed var(--border-subtle)',
          background: 'var(--bg-panel)', cursor: 'pointer', transition: 'border-color 200ms ease',
        }}
          onMouseEnter={(e) => e.currentTarget.style.borderColor = 'var(--nv-green)'}
          onMouseLeave={(e) => e.currentTarget.style.borderColor = 'var(--border-subtle)'}
        >
          <input ref={fileRef} type="file" accept="video/*" onChange={handleUpload} style={{ display: 'none' }} />
          {uploading ? (
            <><Loader2 size={32} style={{ color: 'var(--nv-green)', animation: 'spin 1s linear infinite' }} /><span style={{ color: 'var(--text-muted)' }}>GOP 切分 + Fabric 锚定中...</span></>
          ) : (
            <><Upload size={32} style={{ color: 'var(--text-muted)' }} /><span style={{ color: 'var(--text-muted)' }}>点击或拖放视频文件上传 (自动 GOP 切分 → VIF 指纹 → 链上锚定)</span></>
          )}
        </label>
      )}

      {/* Upload result toast */}
      {uploadResult && !uploadResult.error && (
        <div className="tech-panel" style={{ padding: '12px 16px', marginBottom: '24px', borderLeft: '4px solid var(--nv-green)', display: 'flex', alignItems: 'center', gap: '12px' }}>
          <CheckCircle2 size={18} style={{ color: 'var(--nv-green)' }} />
          <span>已锚定 {uploadResult.gop_count} 个 GOP 至区块 #{uploadResult.block_number || 'pending'}</span>
        </div>
      )}
      {uploadResult?.error && (
        <div className="tech-panel" style={{ padding: '12px 16px', marginBottom: '24px', borderLeft: '4px solid var(--status-err)', display: 'flex', alignItems: 'center', gap: '12px' }}>
          <AlertTriangle size={18} style={{ color: 'var(--status-err)' }} />
          <span>{uploadResult.error}</span>
        </div>
      )}

      <div className="tech-panel" style={{ padding: '22px', marginBottom: '28px', display: 'flex', flexDirection: 'column', gap: '18px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: '16px', alignItems: 'flex-start', flexWrap: 'wrap' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', color: 'var(--nv-green)', marginBottom: '8px' }}>
              <PlayCircle size={18} />
              <h3 style={{ margin: 0, fontSize: '1rem' }}>东八区时间段回放</h3>
            </div>
            <p style={{ margin: 0, color: 'var(--text-muted)', fontSize: '0.84rem', maxWidth: '760px', textWrap: 'pretty' }}>
              选择单路探头，并按东八区时间范围生成连续回放。系统会自动跳过缺失 GOP，只播放当前可恢复的片段。
            </p>
          </div>
          <span className="tag tag-nv" style={{ fontSize: '0.72rem' }}>
            {REPLAY_TIMEZONE} / 最长 30 分钟
          </span>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'minmax(220px, 1.2fr) repeat(2, minmax(220px, 1fr)) auto', gap: '14px', alignItems: 'end' }}>
          <label style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
              <RadioTower size={12} style={{ verticalAlign: 'middle', marginRight: '6px' }} />
              探头选择
            </span>
            <div style={{ position: 'relative' }}>
              <select
                value={replayDeviceId}
                onChange={(e) => setReplayDeviceId(e.target.value)}
                style={{
                  width: '100%',
                  minHeight: '44px',
                  padding: '10px 40px 10px 12px',
                  background: 'var(--bg-pure)',
                  border: '1px solid var(--border-subtle)',
                  color: 'var(--text-pure)',
                  fontFamily: 'var(--font-data)',
                  fontSize: '0.85rem',
                  appearance: 'none',
                  cursor: 'pointer',
                  fontVariantNumeric: 'tabular-nums',
                }}
              >
                <option value="">-- 选择探头 --</option>
                {devices.map((device) => (
                  <option key={device.device_id} value={device.device_id}>
                    {device.label} ({device.device_id})
                  </option>
                ))}
              </select>
              <ChevronDown size={16} style={{ position: 'absolute', right: '12px', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)', pointerEvents: 'none' }} />
            </div>
          </label>

          <label style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
              <CalendarClock size={12} style={{ verticalAlign: 'middle', marginRight: '6px' }} />
              开始时间（东八区）
            </span>
            <input
              type="datetime-local"
              step="1"
              value={replayStartLocal}
              onChange={(e) => setReplayStartLocal(e.target.value)}
              style={{
                minHeight: '44px',
                padding: '10px 12px',
                background: 'var(--bg-pure)',
                border: '1px solid var(--border-subtle)',
                color: 'var(--text-pure)',
                fontFamily: 'var(--font-data)',
                fontSize: '0.85rem',
                fontVariantNumeric: 'tabular-nums',
              }}
            />
          </label>

          <label style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
              <CalendarClock size={12} style={{ verticalAlign: 'middle', marginRight: '6px' }} />
              结束时间（东八区）
            </span>
            <input
              type="datetime-local"
              step="1"
              value={replayEndLocal}
              onChange={(e) => setReplayEndLocal(e.target.value)}
              style={{
                minHeight: '44px',
                padding: '10px 12px',
                background: 'var(--bg-pure)',
                border: '1px solid var(--border-subtle)',
                color: 'var(--text-pure)',
                fontFamily: 'var(--font-data)',
                fontSize: '0.85rem',
                fontVariantNumeric: 'tabular-nums',
              }}
            />
          </label>

          <button
            type="button"
            className="btn"
            onClick={handleReplayGenerate}
            disabled={replayLoading || !replayDeviceId}
            style={{ minWidth: '148px', alignSelf: 'stretch' }}
          >
            {replayLoading ? <Loader2 size={16} style={{ animation: 'spin 1s linear infinite' }} /> : <PlayCircle size={16} />}
            生成回放
          </button>
        </div>

        {replayError && (
          <div style={{ padding: '12px 14px', borderLeft: '3px solid var(--status-err)', background: 'rgba(239,68,68,0.08)', color: 'var(--status-err)', fontSize: '0.82rem' }}>
            {replayError}
          </div>
        )}

        {replayUrl && replaySummary && (
          <div style={{ border: '1px solid var(--border-subtle)', background: 'var(--bg-pure)', boxShadow: '0 12px 32px rgba(0,0,0,0.18)' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '16px', padding: '14px 16px', borderBottom: '1px solid var(--border-subtle)', flexWrap: 'wrap' }}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                <div style={{ color: 'var(--nv-green)', fontFamily: 'var(--font-heading)', fontSize: '0.88rem' }}>连续回放已生成</div>
                <div style={{ color: 'var(--text-muted)', fontSize: '0.8rem', fontVariantNumeric: 'tabular-nums' }}>
                  探头 {replaySummary.deviceId} · {replaySummary.rangeLabel}
                </div>
              </div>
              <a
                href={replayUrl}
                target="_blank"
                rel="noopener noreferrer"
                style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', color: 'var(--status-info)', textDecoration: 'none', fontSize: '0.82rem' }}
              >
                打开 HLS 播放流 <ExternalLink size={14} />
              </a>
            </div>
            <div style={{ aspectRatio: '16 / 9', background: '#000' }}>
              <HlsPlayer url={replayUrl} autoPlay={false} muted={false} controls />
            </div>
            <div style={{ padding: '12px 16px', color: 'var(--text-muted)', fontSize: '0.78rem', borderTop: '1px solid var(--border-subtle)', textWrap: 'pretty' }}>
              若该时间段中间存在缺失 GOP，播放器会自动跳过空洞片段，仅回放当前可恢复的监控数据。
            </div>
          </div>
        )}
      </div>

      {/* Video grid */}
      {videos.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '60px 0', color: 'var(--text-muted)' }}>暂无归档视频</div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: '16px' }}>
          {videos.map((v, i) => <VideoCard key={v.id} video={v} index={i} onViewCert={handleViewCert} />)}
        </div>
      )}

      {certData && <CertificateCard data={certData} onClose={() => setCertData(null)} />}
    </>
  );
}

/* ── Verify Tab ── */
function VerifyTab() {
  const [verifying, setVerifying] = useState(false);
  const [result, setResult] = useState(null);
  const [selectedExportInfo, setSelectedExportInfo] = useState(null);
  const [isDragActive, setIsDragActive] = useState(false);
  const fileRef = useRef(null);

  const submitExportVerify = async (file) => {
    if (!file) return;

    const parsed = parseExportedSampleFilename(file.name);
    if (!parsed) {
      setSelectedExportInfo(null);
      setResult({ error: '该文件不是 SecureLens 导出样本，请从管理端 IPFS 存储页下载标准 TS 样本后再验证。' });
      if (fileRef.current) fileRef.current.value = '';
      return;
    }

    setIsDragActive(false);
    setSelectedExportInfo(parsed);
    setVerifying(true);
    setResult(null);
    try {
      const res = await verifyExportedSample(file);
      setResult(res);
    } catch (err) {
      setResult({ error: err.message });
    } finally {
      setVerifying(false);
      if (fileRef.current) fileRef.current.value = '';
    }
  };

  const handleExportVerify = async (e) => {
    const file = e.target.files?.[0];
    await submitExportVerify(file);
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    if (verifying) return;
    setIsDragActive(true);
  };

  const handleDragLeave = (e) => {
    if (e.currentTarget.contains(e.relatedTarget)) return;
    setIsDragActive(false);
  };

  const handleDrop = async (e) => {
    e.preventDefault();
    if (verifying) return;
    setIsDragActive(false);
    const file = e.dataTransfer.files?.[0];
    await submitExportVerify(file);
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      <div className="tech-panel" style={{ padding: '24px' }}>
        <h3 style={{ margin: '0 0 16px', color: 'var(--nv-green)', fontSize: '1rem' }}>[ 三态完整性验证 ]</h3>
        <div style={{ marginBottom: '16px', color: 'var(--text-muted)', fontSize: '0.82rem', lineHeight: 1.7, textWrap: 'pretty' }}>
          直接上传从管理端 IPFS 存储页导出的 `TS` 样本，或经过“一键篡改”子页生成后的篡改版样本。系统会先校验文件名协议，再自动定位设备和画面时间段，进入闭环验证。
        </div>
        {selectedExportInfo ? (
          <div className="tech-panel" style={{ padding: '14px 16px', marginBottom: '16px', border: '1px solid var(--border-subtle)', background: 'rgba(118, 185, 0, 0.04)' }}>
            <div style={{ color: 'var(--nv-green)', fontFamily: 'var(--font-heading)', fontSize: '0.84rem', marginBottom: '8px' }}>已识别样本协议</div>
            <div style={{ display: 'grid', gap: '4px', color: 'var(--text-muted)', fontSize: '0.8rem', fontVariantNumeric: 'tabular-nums' }}>
              <div>设备: {selectedExportInfo.deviceId}</div>
              <div>实际时间段: {formatVerifyTimestamp(selectedExportInfo.actualStartTime)} 至 {formatVerifyTimestamp(selectedExportInfo.actualEndTime)}</div>
              <div>文件名声明 GOP: {selectedExportInfo.expectedGopCount} / 缺口标记: {selectedExportInfo.gapFlag ? 'gap1 非连续' : 'gap0 连续'}</div>
            </div>
          </div>
        ) : null}
        <div>
          <label style={{ display: 'block', fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '6px' }}>上传管理端导出的 TS 样本</label>
          <label
            onDragEnter={handleDragOver}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '8px',
              minHeight: '70px',
              padding: '16px',
              border: `1px dashed ${isDragActive ? 'rgba(118, 185, 0, 0.8)' : 'var(--border-subtle)'}`,
              background: isDragActive ? 'rgba(118, 185, 0, 0.08)' : 'transparent',
              boxShadow: isDragActive ? '0 0 0 1px rgba(118, 185, 0, 0.28), 0 12px 32px rgba(118, 185, 0, 0.12)' : 'none',
              cursor: verifying ? 'wait' : 'pointer',
              transform: isDragActive ? 'translateY(-1px)' : 'translateY(0)',
              transitionProperty: 'border-color, background-color, box-shadow, transform',
              transitionDuration: '150ms',
              transitionTimingFunction: 'cubic-bezier(0.2, 0, 0, 1)',
            }}
          >
            <input ref={fileRef} type="file" accept=".ts,video/*" onChange={handleExportVerify} style={{ display: 'none' }} />
            {verifying ? (
              <><Loader2 size={18} style={{ color: 'var(--nv-green)', animation: 'spin 1s linear infinite' }} /><span style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>样本验证中...</span></>
            ) : isDragActive ? (
              <><Upload size={18} style={{ color: 'var(--nv-green)' }} /><span style={{ color: 'var(--nv-green)', fontSize: '0.85rem' }}>松开即可上传 SecureLens 导出的 TS 样本</span></>
            ) : (
              <><Upload size={18} style={{ color: 'var(--text-muted)' }} /><span style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>拖动文件到这里，或点击选择 SecureLens 导出的 TS 样本</span></>
            )}
          </label>
        </div>
      </div>

      {/* Results */}
      {result && !result.error && (
        <div style={{ display: 'flex', gap: '24px', flexWrap: 'wrap', alignItems: 'stretch' }}>
          <div className="tech-panel" style={{ 
            padding: '24px', 
            flex: '0 1 340px', 
            minWidth: '300px', 
            display: 'flex', 
            flexDirection: 'column', 
            gap: '24px',
            boxShadow: '0 4px 20px rgba(0, 0, 0, 0.2), inset 0 1px 0 rgba(255, 255, 255, 0.05)',
            borderRadius: '12px'
          }}>
            <div style={{ display: 'flex', justifyContent: 'center' }}>
              <RiskGauge status={result.overall_status} risk={result.overall_risk} size={240} />
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: '12px' }}>
              <div style={{ 
                padding: '16px', 
                background: 'rgba(255,255,255,0.03)', 
                borderRadius: '8px',
                border: '1px solid var(--border-subtle)',
                boxShadow: 'inset 0 1px 0 rgba(255, 255, 255, 0.02)'
              }}>
                <div style={{ color: 'var(--text-dim)', fontSize: '0.75rem', marginBottom: '8px', letterSpacing: '0.06em', textTransform: 'uppercase' }}>
                  {result.verify_mode === 'export_sample' ? '参考 GOP' : '原始 GOP'}
                </div>
                <div style={{ color: 'var(--text-pure)', fontFamily: 'var(--font-heading)', fontSize: '1.4rem', lineHeight: 1, fontVariantNumeric: 'tabular-nums' }}>
                  {result.verify_mode === 'export_sample' ? result.matched_gop_count : result.original_gop_count}
                </div>
              </div>
              <div style={{ 
                padding: '16px', 
                background: 'rgba(255,255,255,0.03)', 
                borderRadius: '8px',
                border: '1px solid var(--border-subtle)',
                boxShadow: 'inset 0 1px 0 rgba(255, 255, 255, 0.02)'
              }}>
                <div style={{ color: 'var(--text-dim)', fontSize: '0.75rem', marginBottom: '8px', letterSpacing: '0.06em', textTransform: 'uppercase' }}>当前 GOP</div>
                <div style={{ color: 'var(--text-pure)', fontFamily: 'var(--font-heading)', fontSize: '1.4rem', lineHeight: 1, fontVariantNumeric: 'tabular-nums' }}>
                  {result.current_gop_count}
                </div>
              </div>
            </div>

            {result.verify_mode === 'export_sample' ? (
              <div style={{ 
                padding: '16px', 
                borderRadius: '8px',
                border: '1px solid var(--border-subtle)', 
                background: 'rgba(255,255,255,0.02)', 
                display: 'flex', 
                flexDirection: 'column', 
                gap: '12px' 
              }}>
                <div style={{ color: 'var(--nv-green)', fontFamily: 'var(--font-heading)', fontSize: '0.85rem', letterSpacing: '0.04em' }}>样本参考范围</div>
                <div style={{ display: 'grid', gap: '8px', color: 'var(--text-muted)', fontSize: '0.85rem', lineHeight: 1.5, fontVariantNumeric: 'tabular-nums' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: 'var(--text-dim)' }}>设备</span>
                    <span style={{ color: 'var(--text-pure)', fontWeight: 500 }}>{result.reference_device_id}</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: 'var(--text-dim)' }}>开始</span>
                    <span>{formatVerifyTimestamp(result.reference_start_time)}</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: 'var(--text-dim)' }}>结束</span>
                    <span>{formatVerifyTimestamp(result.reference_end_time)}</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', borderTop: '1px dashed var(--border-subtle)', paddingTop: '10px', marginTop: '2px' }}>
                    <span style={{ color: 'var(--text-dim)' }}>连续性</span>
                    <span style={{ color: result.gap_flag ? 'var(--status-warn)' : 'var(--nv-green)', fontWeight: 500 }}>
                      {result.gap_flag ? 'gap1 非连续样本' : 'gap0 连续样本'}
                    </span>
                  </div>
                </div>
              </div>
            ) : null}
          </div>
          <div className="tech-panel" style={{ 
            padding: '24px', 
            flex: '1 1 420px', 
            minWidth: 'min(420px, 100%)',
            display: 'flex',
            flexDirection: 'column',
            boxShadow: '0 4px 20px rgba(0, 0, 0, 0.2), inset 0 1px 0 rgba(255, 255, 255, 0.05)',
            borderRadius: '12px'
          }}>
            <h4 style={{ margin: '0 0 16px', color: 'var(--nv-green)', fontSize: '1.05rem', letterSpacing: '0.04em' }}>[ PER-GOP 明细 ]</h4>
            <div style={{ flex: 1, minHeight: 0 }}>
              <GopResultsTable gopResults={result.gop_results} />
            </div>
          </div>
        </div>
      )}
      {result?.error && (
        <div className="tech-panel" style={{ padding: '16px', borderLeft: '4px solid var(--status-err)' }}>
          <AlertTriangle size={16} style={{ color: 'var(--status-err)', verticalAlign: 'middle', marginRight: '8px' }} />
          {result.error}
        </div>
      )}
    </div>
  );
}

/* ── Tamper Tab ── */
function TamperTab() {
  const [selectedFile, setSelectedFile] = useState(null);
  const [selectedExportInfo, setSelectedExportInfo] = useState(null);
  const [result, setResult] = useState(null);
  const [tampering, setTampering] = useState(false);
  const [isDragActive, setIsDragActive] = useState(false);
  const fileRef = useRef(null);

  const handleCandidateFile = (file) => {
    if (!file) return;
    const parsed = parseExportedSampleFilename(file.name);
    if (!parsed) {
      setSelectedFile(null);
      setSelectedExportInfo(null);
      setResult({ error: '该文件不是 SecureLens 标准导出样本，请先从管理端 IPFS 存储页下载 TS 样本。' });
      if (fileRef.current) fileRef.current.value = '';
      return;
    }

    setSelectedFile(file);
    setSelectedExportInfo(parsed);
    setResult(null);
  };

  const submitTamper = async () => {
    if (!selectedFile) return;
    setTampering(true);
    setResult(null);
    try {
      const res = await generateTamperedExportSample(selectedFile);
      setResult({
        ...res,
        download_url: buildApiUrl(res.download_url),
        preview_playlist_url: buildApiUrl(res.preview_playlist_url),
      });
    } catch (err) {
      setResult({ error: err.message });
    } finally {
      setTampering(false);
    }
  };

  const handleFileChange = (e) => {
    const file = e.target.files?.[0];
    handleCandidateFile(file);
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    if (tampering) return;
    setIsDragActive(true);
  };

  const handleDragLeave = (e) => {
    if (e.currentTarget.contains(e.relatedTarget)) return;
    setIsDragActive(false);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    if (tampering) return;
    setIsDragActive(false);
    const file = e.dataTransfer.files?.[0];
    handleCandidateFile(file);
  };

  const attemptColors = {
    TAMPERED: 'var(--status-err)',
    RE_ENCODED: 'var(--status-warn)',
    INTACT: 'var(--nv-green)',
    ERROR: 'var(--text-muted)',
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      <div className="tech-panel" style={{ padding: '24px', display: 'grid', gap: '20px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: '16px', alignItems: 'flex-start', flexWrap: 'wrap' }}>
          <div>
            <h3 style={{ margin: 0, color: 'var(--status-err)', fontSize: '1rem' }}>[ 一键替帧篡改 ]</h3>
          </div>
          <div style={{
            padding: '10px 12px',
            borderRadius: '12px',
            background: 'rgba(255, 90, 90, 0.08)',
            border: '1px solid rgba(255, 90, 90, 0.16)',
            color: 'var(--status-err)',
            fontSize: '0.74rem',
            letterSpacing: '0.06em',
            textTransform: 'uppercase',
            fontVariantNumeric: 'tabular-nums',
          }}>
            Default / Frame Replace / 2.5s
          </div>
        </div>

        <label
          onDragEnter={handleDragOver}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '8px',
            minHeight: '82px',
            padding: '18px',
            border: `1px dashed ${isDragActive ? 'rgba(255, 90, 90, 0.85)' : 'var(--border-subtle)'}`,
            background: isDragActive ? 'rgba(255, 90, 90, 0.07)' : 'transparent',
            boxShadow: isDragActive ? '0 0 0 1px rgba(255, 90, 90, 0.24), 0 16px 36px rgba(255, 90, 90, 0.12)' : 'none',
            cursor: tampering ? 'wait' : 'pointer',
            transform: isDragActive ? 'translateY(-1px)' : 'translateY(0)',
            transitionProperty: 'border-color, background-color, box-shadow, transform',
            transitionDuration: '150ms',
            transitionTimingFunction: 'cubic-bezier(0.2, 0, 0, 1)',
          }}
        >
          <input ref={fileRef} type="file" accept=".ts,video/*" onChange={handleFileChange} style={{ display: 'none' }} />
          {tampering ? (
            <><Loader2 size={18} style={{ color: 'var(--status-err)', animation: 'spin 1s linear infinite' }} /><span style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>篡改样本生成中...</span></>
          ) : isDragActive ? (
            <><Upload size={18} style={{ color: 'var(--status-err)' }} /><span style={{ color: 'var(--status-err)', fontSize: '0.85rem' }}>松开即可导入标准 TS 样本</span></>
          ) : (
            <><Upload size={18} style={{ color: 'var(--text-muted)' }} /><span style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>拖动文件到这里，或点击选择管理端导出的 TS 样本</span></>
          )}
        </label>

        {selectedExportInfo ? (
          <div className="tech-panel" style={{ padding: '16px 18px', border: '1px solid var(--border-subtle)', background: 'rgba(255, 255, 255, 0.02)' }}>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '10px 18px', color: 'var(--text-muted)', fontSize: '0.8rem', fontVariantNumeric: 'tabular-nums' }}>
              <div>原文件名: <span style={{ color: 'var(--text-pure)' }}>{selectedExportInfo.filename}</span></div>
              <div>设备: <span style={{ color: 'var(--text-pure)' }}>{selectedExportInfo.deviceId}</span></div>
              <div>时间段: <span style={{ color: 'var(--text-pure)' }}>{formatVerifyTimestamp(selectedExportInfo.actualStartTime)} 至 {formatVerifyTimestamp(selectedExportInfo.actualEndTime)}</span></div>
              <div>声明 GOP: <span style={{ color: 'var(--text-pure)' }}>{selectedExportInfo.expectedGopCount}</span> / 连续性: <span style={{ color: selectedExportInfo.gapFlag ? 'var(--status-warn)' : 'var(--nv-green)' }}>{selectedExportInfo.gapFlag ? 'gap1 非连续' : 'gap0 连续'}</span></div>
            </div>
          </div>
        ) : null}

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '12px', alignItems: 'center', flexWrap: 'wrap' }}>
          <button
            type="button"
            className="btn"
            onClick={submitTamper}
            disabled={!selectedFile || tampering}
            style={{ minWidth: '178px' }}
          >
            {tampering ? <Loader2 size={16} style={{ animation: 'spin 1s linear infinite' }} /> : <AlertTriangle size={16} />}
            生成篡改样本
          </button>
        </div>
      </div>

      {result && !result.error ? (
        <>
          <div style={{ display: 'flex', gap: '24px', flexWrap: 'wrap', alignItems: 'stretch' }}>
            <div className="tech-panel" style={{ padding: '24px', flex: '0 1 360px', minWidth: '320px', display: 'flex', flexDirection: 'column', gap: '20px', borderRadius: '12px', boxShadow: '0 4px 20px rgba(0, 0, 0, 0.2), inset 0 1px 0 rgba(255, 255, 255, 0.05)' }}>
              <div style={{ display: 'flex', justifyContent: 'center' }}>
                <RiskGauge status={result.overall_status} risk={result.overall_risk} size={220} />
              </div>

              <div style={{ display: 'grid', gap: '12px' }}>
                <div style={{ padding: '16px', background: 'rgba(255,255,255,0.03)', borderRadius: '10px', border: '1px solid var(--border-subtle)' }}>
                  <div style={{ color: 'var(--text-dim)', fontSize: '0.74rem', letterSpacing: '0.06em', textTransform: 'uppercase', marginBottom: '8px' }}>下载文件名</div>
                  <div style={{ color: 'var(--text-pure)', fontSize: '0.95rem', lineHeight: 1.5, wordBreak: 'break-all' }}>{result.download_filename}</div>
                </div>
                <div style={{ padding: '16px', background: 'rgba(255,255,255,0.03)', borderRadius: '10px', border: '1px solid var(--border-subtle)' }}>
                  <div style={{ color: 'var(--text-dim)', fontSize: '0.74rem', letterSpacing: '0.06em', textTransform: 'uppercase', marginBottom: '8px' }}>替帧窗口</div>
                  <div style={{ display: 'grid', gap: '4px', color: 'var(--text-muted)', fontSize: '0.82rem', fontVariantNumeric: 'tabular-nums' }}>
                    <div>篡改时长: <span style={{ color: 'var(--text-pure)' }}>{Number(result.tamper_meta?.replace_seconds || 0).toFixed(1)}s</span></div>
                    <div>替换源: <span style={{ color: 'var(--text-pure)' }}>{Number(result.tamper_meta?.source_start || 0).toFixed(2)}s - {Number(result.tamper_meta?.source_end || 0).toFixed(2)}s</span></div>
                    <div>被篡改区: <span style={{ color: 'var(--status-err)' }}>{Number(result.tamper_meta?.tamper_start || 0).toFixed(2)}s - {Number(result.tamper_meta?.tamper_end || 0).toFixed(2)}s</span></div>
                  </div>
                </div>
              </div>

              <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
                <a href={result.download_url} style={{ textDecoration: 'none' }} className="btn btn-primary">
                  <Download size={14} />
                  下载篡改样本
                </a>
                <a href={result.preview_playlist_url} target="_blank" rel="noopener noreferrer" style={{ textDecoration: 'none' }} className="btn btn-ghost">
                  <ExternalLink size={14} />
                  打开 HLS 预览
                </a>
              </div>
            </div>

            <div className="tech-panel" style={{ padding: '0', flex: '1 1 520px', minWidth: 'min(520px, 100%)', overflow: 'hidden', borderRadius: '12px', boxShadow: '0 4px 20px rgba(0, 0, 0, 0.2), inset 0 1px 0 rgba(255, 255, 255, 0.05)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', alignItems: 'center', padding: '18px 20px', borderBottom: '1px solid var(--border-subtle)', flexWrap: 'wrap' }}>
                <div />
                <div style={{ color: 'var(--text-dim)', fontSize: '0.76rem', fontVariantNumeric: 'tabular-nums' }}>
                  preview {Number(result.tamper_meta?.preview_duration_seconds || 0).toFixed(1)}s
                </div>
              </div>
              <div style={{ aspectRatio: '16 / 9', background: '#000' }}>
                <HlsPlayer url={result.preview_playlist_url} autoPlay={false} muted={false} controls />
              </div>
            </div>
          </div>

          {result.attempts?.length ? (
            <div className="tech-panel" style={{ padding: '18px 20px' }}>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '12px' }}>
                {result.attempts.map((attempt) => (
                  <div key={`${attempt.replace_seconds}-${attempt.status}`} style={{ padding: '14px 16px', borderRadius: '10px', border: '1px solid var(--border-subtle)', background: 'rgba(255,255,255,0.02)' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: '10px', alignItems: 'center', marginBottom: '8px' }}>
                      <span style={{ color: 'var(--text-dim)', fontSize: '0.74rem', textTransform: 'uppercase', letterSpacing: '0.06em' }}>{Number(attempt.replace_seconds || 0).toFixed(1)}s</span>
                      <span style={{ color: attemptColors[attempt.status] || 'var(--text-muted)', fontSize: '0.8rem', fontWeight: 600 }}>{attempt.status}</span>
                    </div>
                    {attempt.error ? (
                      <div style={{ color: 'var(--status-warn)', fontSize: '0.78rem', lineHeight: 1.5 }}>{attempt.error}</div>
                    ) : (
                      <div style={{ display: 'grid', gap: '4px', color: 'var(--text-muted)', fontSize: '0.78rem', fontVariantNumeric: 'tabular-nums' }}>
                        <div>风险值: <span style={{ color: 'var(--text-pure)' }}>{Number(attempt.risk || 0).toFixed(4)}</span></div>
                        <div>当前 GOP: <span style={{ color: 'var(--text-pure)' }}>{attempt.current_gop_count}</span></div>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          ) : null}
        </>
      ) : null}

      {result?.error ? (
        <div className="tech-panel" style={{ padding: '16px', borderLeft: '4px solid var(--status-err)' }}>
          <AlertTriangle size={16} style={{ color: 'var(--status-err)', verticalAlign: 'middle', marginRight: '8px' }} />
          {result.error}
        </div>
      ) : null}
    </div>
  );
}

/* ── History Tab ── */
function HistoryTab() {
  const [records, setRecords] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getVerifyHistory(50).then(r => setRecords(r.history || [])).catch(() => {}).finally(() => setLoading(false));
  }, []);

  const statusCfg = {
    INTACT:     { color: 'var(--nv-green)',   bg: 'var(--nv-green-dim)',    label: '完好' },
    RE_ENCODED: { color: 'var(--status-warn)', bg: 'var(--status-warn-dim)', label: '转码' },
    TAMPERED:   { color: 'var(--status-err)',  bg: 'var(--status-err-dim)',  label: '篡改嫌疑' },
  };

  if (loading) return <div style={{ textAlign: 'center', padding: '60px 0', color: 'var(--text-muted)' }}>加载中...</div>;
  if (!records.length) return <div style={{ textAlign: 'center', padding: '60px 0', color: 'var(--text-muted)' }}>暂无验证记录</div>;

  return (
    <div className="tech-panel" style={{ 
      padding: '0', 
      overflow: 'hidden',
      borderRadius: '12px',
      boxShadow: '0 4px 20px rgba(0, 0, 0, 0.2), inset 0 1px 0 rgba(255, 255, 255, 0.05)',
      border: '1px solid var(--border-subtle)',
    }}>
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', minWidth: '940px' }}>
          <thead>
            <tr style={{ background: 'rgba(255,255,255,0.02)', borderBottom: '1px solid var(--border-subtle)' }}>
              <th style={{ padding: '16px 20px', color: 'var(--text-dim)', fontSize: '0.75rem', fontWeight: 600, letterSpacing: '0.04em' }}>验证 ID</th>
              <th style={{ padding: '16px 20px', color: 'var(--text-dim)', fontSize: '0.75rem', fontWeight: 600, letterSpacing: '0.04em', width: '112px' }}>模式</th>
              <th style={{ padding: '16px 20px', color: 'var(--text-dim)', fontSize: '0.75rem', fontWeight: 600, letterSpacing: '0.04em' }}>参考对象</th>
              <th style={{ padding: '16px 20px', color: 'var(--text-dim)', fontSize: '0.75rem', fontWeight: 600, letterSpacing: '0.04em' }}>上传样本</th>
              <th style={{ padding: '16px 20px', color: 'var(--text-dim)', fontSize: '0.75rem', fontWeight: 600, letterSpacing: '0.04em', textAlign: 'center' }}>状态</th>
              <th style={{ padding: '16px 20px', color: 'var(--text-dim)', fontSize: '0.75rem', fontWeight: 600, letterSpacing: '0.04em', textAlign: 'right' }}>风险评级</th>
              <th style={{ padding: '16px 20px', color: 'var(--text-dim)', fontSize: '0.75rem', fontWeight: 600, letterSpacing: '0.04em', textAlign: 'right' }}>时间</th>
            </tr>
          </thead>
          <tbody>
            {records.map((r, i) => {
              const cfg = statusCfg[r.overall_status] || statusCfg.TAMPERED;
              const isExportSample = r.verify_mode === 'export_sample';
              return (
                <tr key={r.id} style={{ 
                  borderBottom: i === records.length - 1 ? 'none' : '1px solid rgba(255,255,255,0.04)',
                  transition: 'background-color 0.2s ease',
                  backgroundColor: 'transparent',
                }}
                onMouseEnter={(e) => e.currentTarget.style.backgroundColor = 'rgba(255,255,255,0.02)'}
                onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'transparent'}
                >
                  <td style={{ padding: '16px 20px', color: 'var(--text-pure)', fontFamily: 'var(--font-data)', fontSize: '0.85rem' }}>
                    {r.id?.toString().slice(0, 8)}<span style={{ color: 'var(--text-dim)' }}>...</span>
                  </td>
                  <td style={{ padding: '16px 20px', whiteSpace: 'nowrap' }}>
                    <span style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      minWidth: '72px',
                      whiteSpace: 'nowrap',
                      padding: '6px 10px',
                      background: 'rgba(255,255,255,0.04)',
                      borderRadius: '8px',
                      color: 'var(--text-muted)',
                      fontSize: '0.75rem',
                      lineHeight: 1,
                      boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.02)',
                    }}>
                      {isExportSample ? '导出样本' : '原始视频'}
                    </span>
                  </td>
                  <td style={{ padding: '16px 20px', color: 'var(--text-muted)', fontSize: '0.8rem', lineHeight: 1.5, fontVariantNumeric: 'tabular-nums' }}>
                    {isExportSample ? (
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                        <div style={{ color: 'var(--text-pure)' }}>{r.reference_device_id || '—'} <span style={{ color: r.gap_flag ? 'var(--status-warn)' : 'var(--text-dim)', fontSize: '0.7rem' }}>{r.gap_flag ? '(gap1)' : '(gap0)'}</span></div>
                        <div style={{ color: 'var(--text-dim)', fontSize: '0.75rem' }}>{formatVerifyTimestamp(r.reference_start_time)} <span style={{opacity: 0.5}}>至</span> {formatVerifyTimestamp(r.reference_end_time)}</div>
                      </div>
                    ) : (
                      <span style={{ fontFamily: 'var(--font-data)' }}>{r.original_video_id?.slice(0, 20) || '—'}</span>
                    )}
                  </td>
                  <td style={{ padding: '16px 20px', color: 'var(--text-dim)', fontSize: '0.8rem', maxWidth: '240px' }}>
                    <div style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={r.uploaded_filename}>
                      {r.uploaded_filename}
                    </div>
                  </td>
                  <td style={{ padding: '16px 20px', textAlign: 'center' }}>
                    <span style={{ 
                      display: 'inline-flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      whiteSpace: 'nowrap',
                      padding: '4px 12px', 
                      fontSize: '0.75rem', 
                      background: cfg.bg, 
                      color: cfg.color, 
                      borderRadius: '100px',
                      border: `1px solid ${cfg.color}30`,
                      fontWeight: 600,
                      letterSpacing: '0.04em',
                      boxShadow: `0 2px 8px ${cfg.color}15`
                    }}>{cfg.label}</span>
                  </td>
                  <td style={{ padding: '16px 20px', textAlign: 'right', color: cfg.color, fontFamily: 'var(--font-heading)', fontSize: '0.95rem', fontWeight: 600, fontVariantNumeric: 'tabular-nums' }}>
                    {(r.overall_risk * 100).toFixed(1)}%
                  </td>
                  <td style={{ padding: '16px 20px', textAlign: 'right', color: 'var(--text-muted)', fontFamily: 'var(--font-data)', fontSize: '0.8rem', fontVariantNumeric: 'tabular-nums' }}>
                    {r.created_at ? new Date(r.created_at * 1000).toLocaleString('zh-CN', { hour12: false }) : '—'}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
