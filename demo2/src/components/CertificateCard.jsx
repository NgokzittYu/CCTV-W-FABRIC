import { X, ShieldCheck, Hash, Blocks, Clock, FileVideo, Layers } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

/**
 * Certificate modal showing full evidence details for a video.
 */
export default function CertificateCard({ data, onClose }) {
  if (!data) return null;

  const rows = [
    { icon: Hash, label: '视频 ID', value: data.id, mono: true },
    { icon: FileVideo, label: '文件名', value: data.filename },
    { icon: Layers, label: 'GOP 数量', value: data.gop_count },
    { icon: ShieldCheck, label: 'Merkle Root', value: data.merkle_root, mono: true, truncate: true },
    { icon: Blocks, label: 'TX ID', value: data.tx_id, mono: true, truncate: true },
    { icon: Blocks, label: '区块高度', value: data.block_number ?? '—' },
    { icon: Clock, label: '存证时间', value: data.created_at ? new Date(data.created_at * 1000).toLocaleString('zh-CN') : '—' },
  ];

  return (
    <AnimatePresence>
      <motion.div
        className="cert-overlay"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        onClick={onClose}
      >
        <motion.div
          className="cert-modal"
          initial={{ opacity: 0, scale: 0.92, y: 20 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.92, y: 20 }}
          transition={{ duration: 0.35, ease: [0.23, 1, 0.32, 1] }}
          onClick={(e) => e.stopPropagation()}
        >
          {/* Header */}
          <div className="cert-header">
            <div className="cert-header-icon">
              <ShieldCheck size={22} />
            </div>
            <div>
              <h3>存证证书</h3>
              <p className="text-muted" style={{ fontSize: '0.8rem' }}>
                该视频已通过 Hyperledger Fabric 联盟链锚定
              </p>
            </div>
            <button className="cert-close" onClick={onClose}>
              <X size={18} />
            </button>
          </div>

          {/* Body */}
          <div className="cert-body">
            {rows.map((row, i) => {
              const Icon = row.icon;
              return (
                <div key={i} className="cert-row">
                  <div className="cert-row-label">
                    <Icon size={14} />
                    <span>{row.label}</span>
                  </div>
                  <div
                    className={`cert-row-value ${row.mono ? 'mono' : ''}`}
                    title={row.truncate ? String(row.value) : undefined}
                  >
                    {row.truncate && typeof row.value === 'string' && row.value.length > 24
                      ? row.value.slice(0, 12) + '...' + row.value.slice(-12)
                      : row.value}
                  </div>
                </div>
              );
            })}
          </div>

          {/* GOP list */}
          {data.gops && data.gops.length > 0 && (
            <div className="cert-gops">
              <h4 style={{ marginBottom: 12, fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                GOP 详情 ({data.gops.length} 段)
              </h4>
              <div className="cert-gops-list">
                {data.gops.slice(0, 20).map((gop, i) => (
                  <div key={i} className="cert-gop-item">
                    <span className="cert-gop-idx">#{gop.gop_index}</span>
                    <span className="mono" style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>
                      {gop.sha256?.slice(0, 16)}...
                    </span>
                    <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>
                      {gop.frame_count} frames
                    </span>
                  </div>
                ))}
                {data.gops.length > 20 && (
                  <p className="text-muted" style={{ fontSize: '0.75rem', textAlign: 'center', padding: 8 }}>
                    ... 还有 {data.gops.length - 20} 段
                  </p>
                )}
              </div>
            </div>
          )}

          {/* Stamp */}
          <div className="cert-stamp">
            <ShieldCheck size={16} />
            <span>Fabric 联盟链存证 · 防篡改凭证</span>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}
