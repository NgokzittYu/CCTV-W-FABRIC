import { X, ShieldCheck, Hash, Blocks, Clock, FileVideo, Layers, Fingerprint, PlayCircle, ExternalLink } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import HlsPlayer from './HlsPlayer';

export default function CertificateCard({ data, onClose }) {
  if (!data) return null;

  const rows = [
    { icon: Hash, label: '系统哈希', value: data.id },
    { icon: FileVideo, label: '源文件', value: data.filename },
    { icon: Layers, label: 'GOP分段', value: data.gop_count },
    { icon: Fingerprint, label: '默克尔根', value: data.merkle_root || 'AWAITING_SYNC...' },
    { icon: Blocks, label: '交易号', value: data.tx_id || 'PENDING...' },
    { icon: Blocks, label: '区块高度', value: data.block_number ?? 'null' },
    { icon: Clock, label: '时间戳', value: data.created_at ? new Date(data.created_at * 1000).toLocaleString('zh-CN', {hour12: false}) : '—' },
  ];

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={onClose}
        style={{
          position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, 
          background: 'rgba(0,0,0,0.85)', backdropFilter: 'blur(4px)',
          display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100, padding: '24px'
        }}
      >
        <motion.div
          className="tech-panel"
          initial={{ opacity: 0, scale: 0.98, y: 10 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.98, y: 10 }}
          transition={{ duration: 0.2, ease: 'easeOut' }}
          onClick={(e) => e.stopPropagation()}
          style={{ width: '100%', maxWidth: '960px', borderTop: '4px solid var(--nv-green)', padding: 0, overflow: 'hidden' }}
        >
          {/* Header */}
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '24px', borderBottom: '1px solid var(--border-subtle)', background: 'var(--bg-panel)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
              <div style={{ padding: '8px', background: 'var(--nv-green)', color: '#000' }}>
                <ShieldCheck size={24} />
              </div>
              <div>
                <h3 style={{ margin: 0, color: 'var(--nv-green)' }}>安全锚定证书</h3>
                <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '4px' }}>Hyperledger Fabric 联盟链 // 不可篡改记录</div>
              </div>
            </div>
            <button className="btn btn-ghost" onClick={onClose} style={{ padding: '8px', minHeight: 'auto' }}><X size={20}/></button>
          </div>

          {/* Body */}
          <div style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: '16px', background: 'var(--bg-pure)' }}>
            {data.playback_playlist_url && (
              <div style={{ border: '1px solid var(--border-subtle)', background: 'var(--bg-panel)' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '14px 16px', borderBottom: '1px solid var(--border-subtle)' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--nv-green)' }}>
                    <PlayCircle size={16} />
                    <span style={{ fontFamily: 'var(--font-heading)', fontSize: '0.9rem' }}>连续播放预览</span>
                  </div>
                  <a
                    href={data.playback_playlist_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', color: 'var(--text-muted)', fontSize: '0.8rem', textDecoration: 'none' }}
                  >
                    打开播放流 <ExternalLink size={13} />
                  </a>
                </div>
                <div style={{ aspectRatio: '16 / 9', background: '#000' }}>
                  <HlsPlayer url={data.playback_playlist_url} autoPlay={false} muted={false} controls />
                </div>
              </div>
            )}

            {rows.map((row, i) => {
              const Icon = row.icon;
              return (
                <div key={i} style={{ display: 'flex', alignItems: 'flex-start', borderBottom: '1px solid var(--border-subtle)', paddingBottom: '8px' }}>
                  <div style={{ width: '220px', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.9rem' }}>
                    <Icon size={14} /> {row.label}
                  </div>
                  <div style={{ flex: 1, fontFamily: 'var(--font-data)', fontSize: '0.9rem', wordBreak: 'break-all', color: 'var(--text-pure)' }}>
                    {row.value}
                  </div>
                </div>
              );
            })}

            {data.gops && data.gops.length > 0 && (
              <div style={{ marginTop: '16px' }}>
                <h4 style={{ color: 'var(--nv-green)', marginBottom: '8px' }}>[ GOP哈希特征向量组 ]</h4>
                <div className="terminal-block" style={{ maxHeight: '200px' }}>
                  {data.gops.slice(0, 20).map((gop, i) => (
                    <div key={i} style={{ display: 'flex', gap: '16px', opacity: 0.8, marginBottom: '4px' }}>
                      <span style={{ width: '60px' }}>第 {gop.gop_index} 段</span>
                      <span style={{ flex: 1 }}>{gop.sha256}</span>
                      <span style={{ width: '80px', textAlign: 'right' }}>{gop.frame_count} 帧</span>
                    </div>
                  ))}
                  {data.gops.length > 20 && <div style={{ opacity: 0.5, marginTop: '8px' }}>... 还有 {data.gops.length - 20} 段隐藏数据</div>}
                </div>
              </div>
            )}
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}
