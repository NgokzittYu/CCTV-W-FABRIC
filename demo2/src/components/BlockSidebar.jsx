import { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Blocks, ChevronLeft, ChevronRight, ChevronDown,
  Hash, Fingerprint, Layers, Clock, RefreshCw, Lock, FileVideo
} from 'lucide-react';
import { getRecentBlocks, getBatchDetails, listVideos, getVideoCertificate } from '../services/api';

export default function BlockSidebar() {
  const [open, setOpen] = useState(false);
  const [blocks, setBlocks] = useState([]);
  const [videos, setVideos] = useState([]);
  const [loading, setLoading] = useState(false);
  const [expandedId, setExpandedId] = useState(null);
  const [expandedType, setExpandedType] = useState(null); // 'block' | 'video'
  const [detail, setDetail] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const [b, v] = await Promise.allSettled([getRecentBlocks(), listVideos()]);
      setBlocks(b.status === 'fulfilled' ? (b.value.blocks || []) : []);
      setVideos(v.status === 'fulfilled' ? (v.value.videos || []) : []);
    } catch {}
    setLoading(false);
  }, []);

  useEffect(() => {
    if (!open) return;
    refresh();
    const t = setInterval(refresh, 15000);
    return () => clearInterval(t);
  }, [open, refresh]);

  const handleExpandBlock = async (batchId) => {
    if (expandedId === batchId) { setExpandedId(null); setDetail(null); return; }
    setExpandedId(batchId); setExpandedType('block'); setDetailLoading(true);
    try { setDetail(await getBatchDetails(batchId)); } catch { setDetail(null); }
    setDetailLoading(false);
  };

  const handleExpandVideo = async (videoId) => {
    if (expandedId === videoId) { setExpandedId(null); setDetail(null); return; }
    setExpandedId(videoId); setExpandedType('video'); setDetailLoading(true);
    try { setDetail(await getVideoCertificate(videoId)); } catch { setDetail(null); }
    setDetailLoading(false);
  };

  return (
    <>
      {/* Toggle tab */}
      <button onClick={() => setOpen(!open)} style={{
        position: 'fixed', right: open ? '400px' : 0, top: '50%', transform: 'translateY(-50%)',
        zIndex: 30, padding: '12px 6px', background: 'var(--bg-panel)',
        border: '1px solid var(--border-subtle)', borderRight: open ? 'none' : undefined,
        color: 'var(--nv-green)', cursor: 'pointer', transition: 'right 250ms ease',
        display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '4px',
      }}>
        {open ? <ChevronRight size={14} /> : <ChevronLeft size={14} />}
        <Blocks size={14} />
        <span style={{ writingMode: 'vertical-rl', fontSize: '0.65rem', fontFamily: 'var(--font-heading)', letterSpacing: '0.1em' }}>链上证据</span>
      </button>

      {/* Panel */}
      <div style={{
        position: 'fixed', top: 0, right: 0, bottom: 0, width: '400px',
        background: 'var(--bg-panel)', borderLeft: '1px solid var(--border-subtle)',
        zIndex: 25, transform: open ? 'translateX(0)' : 'translateX(100%)',
        transition: 'transform 250ms ease', display: 'flex', flexDirection: 'column',
      }}>
        {/* Header */}
        <div style={{ padding: '16px', borderBottom: '1px solid var(--border-subtle)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Blocks size={16} color="var(--nv-green)" />
            <span style={{ fontFamily: 'var(--font-heading)', fontSize: '0.9rem', fontWeight: 700 }}>链上锚定证据</span>
          </div>
          <button onClick={refresh} className="btn btn-ghost" style={{ padding: '6px', minHeight: 'auto' }}>
            <RefreshCw size={14} style={loading ? { animation: 'spin 1s linear infinite' } : {}} />
          </button>
        </div>

        <div style={{ flex: 1, overflowY: 'auto', padding: '8px' }}>
          {/* ── Video Evidence Section ── */}
          {videos.length > 0 && (
            <>
              <SectionLabel icon={FileVideo} label="视频证据 (GOP / VIF / SHA-256)" />
              {videos.map((v) => (
                <div key={v.id} style={{ marginBottom: '4px' }}>
                  <RowButton active={expandedId === v.id} onClick={() => handleExpandVideo(v.id)}>
                    <FileVideo size={11} color="var(--status-info)" />
                    {v.block_number != null
                      ? <span style={{ fontWeight: 700, color: 'var(--nv-green)', minWidth: '50px' }}><Lock size={9} style={{ verticalAlign: 'middle' }} /> #{v.block_number}</span>
                      : <span style={{ color: 'var(--status-warn)', fontSize: '0.65rem', minWidth: '50px' }}>PENDING</span>}
                    <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{v.filename}</span>
                    <span className="tag tag-nv" style={{ fontSize: '0.6rem', padding: '1px 5px' }}>{v.gop_count} GOP</span>
                  </RowButton>
                  <ExpandPanel show={expandedId === v.id}>
                    <VideoDetail data={detail} loading={detailLoading} />
                  </ExpandPanel>
                </div>
              ))}
            </>
          )}

          {/* ── Blockchain Blocks Section ── */}
          {blocks.length > 0 && (
            <>
              <SectionLabel icon={Blocks} label={`Fabric 区块 (${blocks.length})`} />
              {blocks.map((b) => (
                <div key={b.batch_id} style={{ marginBottom: '4px' }}>
                  <RowButton active={expandedId === b.batch_id} onClick={() => handleExpandBlock(b.batch_id)}>
                    <Blocks size={11} color="var(--status-info)" />
                    <span style={{ fontWeight: 700, color: 'var(--nv-green)', minWidth: '50px' }}>#{b.block_number}</span>
                    <span style={{ flex: 1, fontSize: '0.65rem', color: 'var(--text-dim)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {b.merkle_root?.slice(0, 16)}...
                    </span>
                    <span className="tag tag-nv" style={{ fontSize: '0.6rem', padding: '1px 5px' }}>{b.event_count}</span>
                  </RowButton>
                  <ExpandPanel show={expandedId === b.batch_id}>
                    <BlockDetail data={detail} loading={detailLoading} />
                  </ExpandPanel>
                </div>
              ))}
            </>
          )}

          {blocks.length === 0 && videos.length === 0 && !loading && (
            <div style={{ padding: '24px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.8rem' }}>暂无链上数据</div>
          )}
        </div>
      </div>
    </>
  );
}

/* ── Shared sub-components ── */

function SectionLabel({ icon: Icon, label }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '6px', padding: '8px 4px 4px', fontSize: '0.7rem', color: 'var(--text-muted)', fontFamily: 'var(--font-heading)', letterSpacing: '0.05em' }}>
      <Icon size={12} /> {label}
    </div>
  );
}

function RowButton({ active, onClick, children }) {
  return (
    <button onClick={onClick} style={{
      width: '100%', display: 'flex', alignItems: 'center', gap: '8px',
      padding: '10px 12px', background: active ? 'var(--bg-surface)' : 'transparent',
      border: '1px solid var(--border-subtle)', cursor: 'pointer',
      color: 'var(--text-pure)', fontFamily: 'var(--font-data)', fontSize: '0.78rem',
      textAlign: 'left', outline: 'none',
    }}>
      {active ? <ChevronDown size={12} color="var(--nv-green)" /> : <ChevronRight size={12} color="var(--text-muted)" />}
      {children}
    </button>
  );
}

function ExpandPanel({ show, children }) {
  return (
    <AnimatePresence initial={false}>
      {show && (
        <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }} transition={{ duration: 0.15 }} style={{ overflow: 'hidden' }}>
          {children}
        </motion.div>
      )}
    </AnimatePresence>
  );
}

/* ── Block detail (Fabric batches) ── */
function BlockDetail({ data, loading }) {
  if (loading) return <div style={{ padding: '12px', fontSize: '0.75rem', color: 'var(--text-muted)' }}>加载中...</div>;
  if (!data) return null;
  return (
    <div style={{ padding: '10px 12px', background: 'var(--bg-surface)', borderLeft: '2px solid var(--nv-green)', margin: '0 0 4px', fontSize: '0.68rem' }}>
      <div style={{ marginBottom: '4px' }}>
        <span style={{ color: 'var(--text-muted)' }}>Merkle Root: </span>
        <span style={{ color: 'var(--nv-green)', wordBreak: 'break-all', fontFamily: 'var(--font-data)' }}>{data.merkle_root}</span>
      </div>
      <div style={{ marginBottom: '4px' }}>
        <span style={{ color: 'var(--text-muted)' }}>TX: </span>
        <span style={{ color: 'var(--status-info)', wordBreak: 'break-all' }}>{data.tx_id?.slice(0, 32)}...</span>
      </div>
      <div style={{ marginBottom: '4px', color: 'var(--text-muted)' }}>
        <Clock size={10} style={{ verticalAlign: 'middle', marginRight: '4px' }} />
        {data.timestamp ? new Date(data.timestamp * 1000).toLocaleString('zh-CN', { hour12: false }) : '—'}
      </div>
      {data.events?.length > 0 && (
        <div style={{ marginTop: '6px', borderTop: '1px solid var(--border-subtle)', paddingTop: '4px' }}>
          <div style={{ color: 'var(--text-muted)', marginBottom: '4px' }}>哈希记录 ({data.events.length})</div>
          {data.events.slice(0, 10).map((evt) => (
            <div key={evt.event_id} style={{ padding: '3px 0', borderBottom: '1px solid var(--border-subtle)', display: 'flex', gap: '4px', alignItems: 'center' }}>
              <Hash size={9} color="var(--status-info)" />
              <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: 'var(--text-pure)', fontSize: '0.65rem' }}>
                {evt.evidence_hash || evt.event_id}
              </span>
            </div>
          ))}
          {data.events.length > 10 && <div style={{ padding: '3px 0', color: 'var(--text-dim)' }}>... +{data.events.length - 10}</div>}
        </div>
      )}
    </div>
  );
}

/* ── Video detail (GOP / VIF / SHA-256) ── */
function VideoDetail({ data, loading }) {
  if (loading) return <div style={{ padding: '12px', fontSize: '0.75rem', color: 'var(--text-muted)' }}>加载 GOP 指纹...</div>;
  if (!data) return null;
  const gops = data.gops || [];
  return (
    <div style={{ padding: '10px 12px', background: 'var(--bg-surface)', borderLeft: '2px solid #bc8cff', margin: '0 0 4px', fontSize: '0.68rem' }}>
      <div style={{ marginBottom: '4px' }}>
        <span style={{ color: 'var(--text-muted)' }}>Merkle Root: </span>
        <span style={{ color: 'var(--nv-green)', wordBreak: 'break-all', fontFamily: 'var(--font-data)' }}>{data.merkle_root}</span>
      </div>
      <div style={{ marginBottom: '4px' }}>
        <span style={{ color: 'var(--text-muted)' }}>TX: </span>
        <span style={{ color: 'var(--status-info)', wordBreak: 'break-all' }}>{data.tx_id || 'pending'}</span>
      </div>
      {gops.length > 0 && (
        <div style={{ marginTop: '6px', borderTop: '1px solid var(--border-subtle)', paddingTop: '4px' }}>
          <div style={{ color: 'var(--text-muted)', marginBottom: '4px' }}>
            <Layers size={10} style={{ verticalAlign: 'middle', marginRight: '4px' }} />GOP 指纹 ({gops.length})
          </div>
          {gops.slice(0, 20).map((g) => (
            <div key={g.gop_index} style={{ padding: '4px 0', borderBottom: '1px solid var(--border-subtle)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '2px' }}>
                <span style={{ color: 'var(--text-muted)' }}>GOP #{g.gop_index}</span>
                <span style={{ color: 'var(--text-muted)' }}>{g.frame_count}帧 / {g.byte_size ? (g.byte_size / 1024).toFixed(0) + 'KB' : '—'}</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '4px', marginBottom: '1px' }}>
                <Hash size={9} color="var(--status-info)" />
                <span style={{ color: 'var(--status-info)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={g.sha256}>{g.sha256}</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                <Fingerprint size={9} color="#bc8cff" />
                <span style={{ color: '#bc8cff', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={g.vif}>{g.vif || '—'}</span>
              </div>
            </div>
          ))}
          {gops.length > 20 && <div style={{ padding: '3px 0', color: 'var(--text-dim)' }}>... +{gops.length - 20}</div>}
        </div>
      )}
    </div>
  );
}
