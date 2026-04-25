import { useState, useEffect } from 'react';
import {
  FileSearch, Blocks, ShieldCheck, ChevronDown, ChevronRight,
  Hash, Clock, Fingerprint, Layers, FileVideo, Lock
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { listVideos, getVideoCertificate } from '../services/api';

export default function EvidencePage() {
  const [videos, setVideos] = useState([]);
  const [loading, setLoading] = useState(true);
  const [expandedId, setExpandedId] = useState(null);
  const [certData, setCertData] = useState(null);
  const [certLoading, setCertLoading] = useState(false);

  useEffect(() => {
    listVideos()
      .then((d) => setVideos(d.videos || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const handleExpand = async (videoId) => {
    if (expandedId === videoId) {
      setExpandedId(null);
      setCertData(null);
      return;
    }
    setExpandedId(videoId);
    setCertLoading(true);
    setCertData(null);
    try {
      const data = await getVideoCertificate(videoId);
      setCertData(data);
    } catch (e) {
      setCertData({ error: e.message });
    } finally {
      setCertLoading(false);
    }
  };

  return (
    <div className="main-content" style={{ padding: '40px' }}>
      <div style={{ paddingBottom: '16px', borderBottom: '1px solid var(--border-subtle)' }}>
        <h2 style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--nv-green)' }}>
          <FileSearch size={24} /> 证据浏览
        </h2>
        <h4 style={{ color: 'var(--text-muted)' }}>
          浏览已锚定的视频证据，查看 GOP 级 SHA-256 / VIF v4 指纹
        </h4>
      </div>

      {/* Video Evidence List */}
      <div style={{ marginTop: '24px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
        {loading ? (
          <div className="terminal-block">正在拉取视频证据索引...</div>
        ) : videos.length === 0 ? (
          <div className="terminal-block" style={{ color: 'var(--text-muted)' }}>[空] // 暂无已锚定视频证据</div>
        ) : (
          videos.map((v, i) => (
            <div key={v.id} className="anim-enter" style={{ animationDelay: `${i * 0.03}s` }}>
              {/* Video Row */}
              <button
                onClick={() => handleExpand(v.id)}
                style={{
                  width: '100%', display: 'flex', alignItems: 'center', gap: '12px',
                  padding: '14px 16px', background: expandedId === v.id ? 'var(--bg-surface)' : 'var(--bg-panel)',
                  border: '1px solid var(--border-subtle)', cursor: 'pointer',
                  borderBottom: expandedId === v.id ? 'none' : undefined,
                  color: 'var(--text-pure)', fontFamily: 'var(--font-data)', fontSize: '0.85rem',
                  textAlign: 'left', outline: 'none', transition: 'background 150ms var(--ease-sharp)',
                }}
              >
                {expandedId === v.id ? <ChevronDown size={16} color="var(--nv-green)" /> : <ChevronRight size={16} color="var(--text-muted)" />}
                <FileVideo size={14} color="var(--status-info)" />
                <span style={{ fontWeight: 700, minWidth: '180px' }}>{v.filename}</span>
                <span className="tag tag-nv"><Layers size={10} /> {v.gop_count} GOPs</span>
                {v.block_number != null && (
                  <span style={{ fontSize: '0.75rem', color: 'var(--nv-green)' }}>
                    <Lock size={10} style={{ verticalAlign: 'middle', marginRight: '4px' }} />
                    Block #{v.block_number}
                  </span>
                )}
                <span style={{ color: 'var(--text-muted)', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontSize: '0.75rem' }}>
                  {v.merkle_root?.slice(0, 16)}...
                </span>
                <span style={{ fontSize: '0.7rem', color: 'var(--text-dim)' }}>
                  {v.created_at ? new Date(v.created_at * 1000).toLocaleString('zh-CN', { hour12: false }) : ''}
                </span>
              </button>

              {/* Expanded GOP Detail */}
              <AnimatePresence initial={false}>
                {expandedId === v.id && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: 'auto', opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    transition={{ duration: 0.2, ease: [0.2, 0, 0, 1] }}
                    style={{ overflow: 'hidden' }}
                  >
                    <div style={{ padding: '16px', background: 'var(--bg-surface)', border: '1px solid var(--border-subtle)', borderTop: 'none' }}>
                      {certLoading ? (
                        <div style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>加载 GOP 指纹数据...</div>
                      ) : certData?.error ? (
                        <div style={{ color: 'var(--status-err)', fontSize: '0.85rem' }}>错误: {certData.error}</div>
                      ) : certData ? (
                        <CertDetail data={certData} />
                      ) : null}
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

function CertDetail({ data }) {
  const gops = data.gops || [];

  return (
    <>
      {/* Video Meta */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '10px', marginBottom: '16px', fontSize: '0.75rem' }}>
        <div>
          <span style={{ color: 'var(--text-muted)' }}>Video ID: </span>
          <span style={{ color: 'var(--text-pure)', wordBreak: 'break-all' }}>{data.id}</span>
        </div>
        <div>
          <span style={{ color: 'var(--text-muted)' }}>TX ID: </span>
          <span style={{ color: 'var(--status-info)', wordBreak: 'break-all' }}>{data.tx_id?.slice(0, 24) || 'pending'}...</span>
        </div>
        <div style={{ gridColumn: '1 / -1' }}>
          <span style={{ color: 'var(--text-muted)' }}>Merkle Root: </span>
          <span style={{ color: 'var(--nv-green)', wordBreak: 'break-all', fontFamily: 'var(--font-data)' }}>{data.merkle_root}</span>
        </div>
      </div>

      {/* GOP Table */}
      <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: '8px' }}>
        GOP 指纹列表 ({gops.length})  —  SHA-256 + VIF v4 (256-bit)
      </div>
      <div className="terminal-block" style={{ maxHeight: '400px' }}>
        {/* Header */}
        <div style={{ display: 'flex', gap: '8px', paddingBottom: '6px', marginBottom: '6px', borderBottom: '1px solid var(--border-subtle)', fontSize: '0.7rem', color: 'var(--text-muted)' }}>
          <span style={{ width: '50px' }}>GOP</span>
          <span style={{ flex: 2 }}>SHA-256</span>
          <span style={{ flex: 2 }}>VIF v4 指纹</span>
          <span style={{ width: '60px', textAlign: 'right' }}>帧数</span>
          <span style={{ width: '70px', textAlign: 'right' }}>大小</span>
        </div>
        {gops.map((g) => (
          <div key={g.gop_index} style={{ display: 'flex', gap: '8px', marginBottom: '3px', fontSize: '0.75rem', alignItems: 'center' }}>
            <span style={{ width: '50px', color: 'var(--text-muted)' }}>#{g.gop_index}</span>
            <span style={{ flex: 2, color: 'var(--status-info)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={g.sha256}>
              <Hash size={10} style={{ verticalAlign: 'middle', marginRight: '2px' }} />
              {g.sha256}
            </span>
            <span style={{ flex: 2, color: '#bc8cff', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={g.vif}>
              <Fingerprint size={10} style={{ verticalAlign: 'middle', marginRight: '2px' }} />
              {g.vif || '—'}
            </span>
            <span style={{ width: '60px', textAlign: 'right', color: 'var(--text-pure)' }}>{g.frame_count}</span>
            <span style={{ width: '70px', textAlign: 'right', color: 'var(--text-muted)' }}>
              {g.byte_size ? (g.byte_size / 1024).toFixed(1) + 'KB' : '—'}
            </span>
          </div>
        ))}
      </div>
    </>
  );
}
