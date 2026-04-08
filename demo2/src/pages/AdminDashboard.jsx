import { useState, useEffect, useCallback } from 'react';
import {
  LayoutDashboard, Video, Upload, RefreshCw, HardDrive, AlertTriangle,
  ShieldCheck, Blocks, Activity, Wifi, WifiOff, FileVideo, Layers, Clock,
  Plus, Search
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { listVideos, uploadVideo, getVideoCertificate } from '../services/api';
import VideoCard from '../components/VideoCard';
import CertificateCard from '../components/CertificateCard';
import AnimatedCounter from '../components/AnimatedCounter';

// ── Mock data for tabs that don't need backend ──
const MOCK_DEVICES = [
  { id: 'cctv-kctmc-apple-01', name: '主楼东门', status: 'online', ip: '192.168.1.101', model: 'DS-2CD2T45' },
  { id: 'cctv-kctmc-apple-02', name: '停车场入口', status: 'online', ip: '192.168.1.102', model: 'DS-2CD2T45' },
  { id: 'cctv-kctmc-apple-03', name: '实验楼走廊', status: 'offline', ip: '192.168.1.103', model: 'DS-2CD2085' },
  { id: 'cctv-kctmc-apple-04', name: '后门通道', status: 'online', ip: '192.168.1.104', model: 'DS-2CD2T45' },
  { id: 'cctv-kctmc-apple-05', name: '图书馆大厅', status: 'online', ip: '192.168.1.105', model: 'DS-2CD2085' },
  { id: 'cctv-kctmc-apple-06', name: '操场西侧', status: 'warning', ip: '192.168.1.106', model: 'DS-2CD2T45' },
];

const MOCK_ALERTS = [
  { id: 1, type: 'tamper', msg: '设备 cctv-03 视频流异常中断', time: '14:32', level: 'high' },
  { id: 2, type: 'offline', msg: '实验楼走廊设备离线超过 10 分钟', time: '14:28', level: 'medium' },
  { id: 3, type: 'chain', msg: 'Fabric 区块高度同步延迟告警', time: '13:45', level: 'low' },
  { id: 4, type: 'storage', msg: 'IPFS 节点 ipfs-2 存储空间不足 (<10%)', time: '12:10', level: 'medium' },
];


export default function AdminDashboard({ activeTab }) {
  switch (activeTab) {
    case 'overview': return <OverviewTab />;
    case 'devices':  return <DevicesTab />;
    case 'archive':  return <ArchiveTab />;
    case 'alerts':   return <AlertsTab />;
    default:         return <OverviewTab />;
  }
}


// ═══════════════════════════════════════════════════════════════
// Tab 1: 监控总览
// ═══════════════════════════════════════════════════════════════
function OverviewTab() {
  const [videos, setVideos] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    listVideos()
      .then((d) => setVideos(d.videos || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const onlineDevices = MOCK_DEVICES.filter((d) => d.status === 'online').length;

  const stats = [
    {
      label: '已存证视频',
      value: videos.length,
      icon: Video,
      color: 'var(--accent-green)',
      bg: 'var(--accent-green-dim)',
    },
    {
      label: '在线设备',
      value: onlineDevices,
      icon: HardDrive,
      color: 'var(--accent-blue)',
      bg: 'var(--accent-blue-dim)',
    },
    {
      label: '链上区块',
      value: videos.length > 0 ? Math.max(...videos.map((v) => v.block_number || 0)) : 0,
      icon: Blocks,
      color: 'var(--accent-purple)',
      bg: 'var(--accent-purple-dim)',
    },
    {
      label: '活跃告警',
      value: MOCK_ALERTS.filter((a) => a.level === 'high').length,
      icon: AlertTriangle,
      color: 'var(--accent-amber)',
      bg: 'var(--accent-amber-dim)',
    },
  ];

  return (
    <div className="dashboard-content">
      <div className="dashboard-header">
        <h2><LayoutDashboard size={22} /> 监控总览</h2>
        <p className="text-muted">系统运行状态概览</p>
      </div>

      {/* Stats Grid */}
      <div className="grid-4 stats-grid">
        {stats.map((s, i) => {
          const Icon = s.icon;
          return (
            <motion.div
              key={i}
              className="stat-card glass-card"
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.08, ease: [0.23, 1, 0.32, 1] }}
            >
              <div className="stat-card-icon" style={{ background: s.bg, color: s.color }}>
                <Icon size={20} />
              </div>
              <div className="stat-card-body">
                <span className="stat-card-value">
                  <AnimatedCounter value={s.value} />
                </span>
                <span className="stat-card-label">{s.label}</span>
              </div>
            </motion.div>
          );
        })}
      </div>

      {/* Recent Activity */}
      <div className="section" style={{ marginTop: 32 }}>
        <h3 style={{ marginBottom: 16 }}>
          <Activity size={18} /> 最近存证
        </h3>
        {loading ? (
          <div className="loading-placeholder">加载中...</div>
        ) : videos.length === 0 ? (
          <div className="empty-state glass-card">
            <Video size={32} style={{ color: 'var(--text-muted)' }} />
            <p>暂无存证视频</p>
            <p className="text-muted" style={{ fontSize: '0.8rem' }}>
              前往「视频存证」上传视频开始使用
            </p>
          </div>
        ) : (
          <div className="recent-list">
            {videos.slice(0, 5).map((v, i) => (
              <div key={v.id} className="recent-item glass-card">
                <FileVideo size={16} style={{ color: 'var(--accent-green)' }} />
                <span className="recent-item-name">{v.filename}</span>
                <span className="badge badge-intact" style={{ fontSize: '0.65rem' }}>
                  <ShieldCheck size={10} /> 已上链
                </span>
                <span className="text-muted" style={{ fontSize: '0.75rem' }}>
                  {v.gop_count} GOPs
                </span>
                <span className="text-muted" style={{ fontSize: '0.7rem' }}>
                  {v.created_at ? new Date(v.created_at * 1000).toLocaleString('zh-CN') : ''}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}


// ═══════════════════════════════════════════════════════════════
// Tab 2: 设备管理 (Mock)
// ═══════════════════════════════════════════════════════════════
function DevicesTab() {
  return (
    <div className="dashboard-content">
      <div className="dashboard-header">
        <h2><HardDrive size={22} /> 设备管理</h2>
        <p className="text-muted">边缘监控设备一览</p>
      </div>

      <div className="grid-3" style={{ marginTop: 24 }}>
        {MOCK_DEVICES.map((device, i) => (
          <motion.div
            key={device.id}
            className="glass-card device-card"
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.06 }}
          >
            <div className="device-card-header">
              <div className="device-card-status">
                {device.status === 'online' && <Wifi size={14} style={{ color: 'var(--accent-green)' }} />}
                {device.status === 'offline' && <WifiOff size={14} style={{ color: 'var(--accent-red)' }} />}
                {device.status === 'warning' && <AlertTriangle size={14} style={{ color: 'var(--accent-amber)' }} />}
                <span className={`badge badge-${device.status === 'online' ? 'intact' : device.status === 'offline' ? 'tampered' : 're-encoded'}`}>
                  {device.status === 'online' ? '在线' : device.status === 'offline' ? '离线' : '警告'}
                </span>
              </div>
              <span className="mono" style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>
                {device.ip}
              </span>
            </div>
            <h4 style={{ marginTop: 12, marginBottom: 4 }}>{device.name}</h4>
            <p className="text-muted" style={{ fontSize: '0.75rem' }}>{device.id}</p>
            <p className="text-muted" style={{ fontSize: '0.7rem', marginTop: 4 }}>型号: {device.model}</p>
          </motion.div>
        ))}
      </div>
    </div>
  );
}


// ═══════════════════════════════════════════════════════════════
// Tab 3: 视频存证 (Real API)
// ═══════════════════════════════════════════════════════════════
function ArchiveTab() {
  const [videos, setVideos] = useState([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState('');
  const [certData, setCertData] = useState(null);

  const refresh = useCallback(() => {
    setLoading(true);
    listVideos()
      .then((d) => setVideos(d.videos || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const handleUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setUploadProgress('正在上传并处理...');
    try {
      const result = await uploadVideo(file);
      if (result.error) {
        setUploadProgress(`错误: ${result.error}`);
      } else {
        setUploadProgress(`✅ 存证成功! Video ID: ${result.video_id}, GOPs: ${result.gop_count}`);
        refresh();
      }
    } catch (err) {
      setUploadProgress(`上传失败: ${err.message}`);
    } finally {
      setUploading(false);
      setTimeout(() => setUploadProgress(''), 5000);
    }
  };

  const handleViewCert = async (videoId) => {
    try {
      const data = await getVideoCertificate(videoId);
      setCertData(data);
    } catch (e) {
      console.error(e);
    }
  };

  return (
    <div className="dashboard-content">
      <div className="dashboard-header">
        <div>
          <h2><Video size={22} /> 视频存证</h2>
          <p className="text-muted">上传视频 → GOP 切分 → VIF 指纹 → Merkle 树 → 链上锚定</p>
        </div>
        <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
          <button className="btn btn-ghost btn-sm" onClick={refresh} disabled={loading}>
            <RefreshCw size={14} className={loading ? 'spin' : ''} /> 刷新
          </button>
          <label className="btn btn-primary btn-sm" style={{ cursor: uploading ? 'wait' : 'pointer' }}>
            <Upload size={14} /> {uploading ? '处理中...' : '上传视频'}
            <input
              type="file"
              accept="video/*"
              hidden
              onChange={handleUpload}
              disabled={uploading}
            />
          </label>
        </div>
      </div>

      {/* Upload progress */}
      <AnimatePresence>
        {uploadProgress && (
          <motion.div
            className="upload-progress glass-card"
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
          >
            {uploadProgress}
          </motion.div>
        )}
      </AnimatePresence>

      {/* Video list */}
      {loading ? (
        <div className="loading-placeholder">加载中...</div>
      ) : videos.length === 0 ? (
        <div className="empty-state glass-card">
          <Upload size={32} style={{ color: 'var(--text-muted)' }} />
          <p>暂无存证视频</p>
          <p className="text-muted" style={{ fontSize: '0.8rem' }}>
            点击「上传视频」开始第一次存证
          </p>
        </div>
      ) : (
        <div className="grid-3" style={{ marginTop: 20 }}>
          {videos.map((v, i) => (
            <VideoCard key={v.id} video={v} index={i} onViewCert={handleViewCert} />
          ))}
        </div>
      )}

      {/* Certificate Modal */}
      {certData && <CertificateCard data={certData} onClose={() => setCertData(null)} />}
    </div>
  );
}


// ═══════════════════════════════════════════════════════════════
// Tab 4: 告警中心 (Mock)
// ═══════════════════════════════════════════════════════════════
function AlertsTab() {
  const levelColors = {
    high: 'var(--accent-red)',
    medium: 'var(--accent-amber)',
    low: 'var(--accent-blue)',
  };

  return (
    <div className="dashboard-content">
      <div className="dashboard-header">
        <h2><AlertTriangle size={22} /> 告警中心</h2>
        <p className="text-muted">系统异常与安全告警</p>
      </div>

      <div className="alerts-list" style={{ marginTop: 20 }}>
        {MOCK_ALERTS.map((alert, i) => (
          <motion.div
            key={alert.id}
            className="glass-card alert-item"
            initial={{ opacity: 0, x: -12 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: i * 0.08 }}
          >
            <div
              className="alert-level-dot"
              style={{ background: levelColors[alert.level] }}
            />
            <div style={{ flex: 1 }}>
              <p style={{ fontSize: '0.85rem', marginBottom: 4 }}>{alert.msg}</p>
              <span className="text-muted" style={{ fontSize: '0.7rem' }}>
                <Clock size={10} /> {alert.time}
              </span>
            </div>
            <span
              className="badge"
              style={{
                background: levelColors[alert.level] + '20',
                color: levelColors[alert.level],
                border: `1px solid ${levelColors[alert.level]}40`,
              }}
            >
              {alert.level === 'high' ? '高危' : alert.level === 'medium' ? '中风险' : '低'}
            </span>
          </motion.div>
        ))}
      </div>
    </div>
  );
}
