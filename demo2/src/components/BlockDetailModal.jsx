import { useEffect } from 'react';
import { createPortal } from 'react-dom';
import { AnimatePresence, motion } from 'framer-motion';
import { Blocks, Clock, Copy, Hash, Layers, Link2, X } from 'lucide-react';

function formatDateTime(timestamp) {
  if (!timestamp) return '—';
  return new Date(Number(timestamp) * 1000).toLocaleString('zh-CN', { hour12: false });
}

function CopyField({ value }) {
  if (!value) return <span style={{ color: 'var(--text-dim)' }}>—</span>;

  return (
    <button
      type="button"
      onClick={() => navigator.clipboard?.writeText(String(value))}
      className="block-detail-copy"
      title="复制"
    >
      <span>{value}</span>
      <Copy size={12} />
    </button>
  );
}

function FingerprintValue({ value }) {
  if (!value) return '—';

  return String(value)
    .match(/.{1,8}/g)
    .map((chunk, index) => (
      <span key={`${chunk}-${index}`} className="block-detail-fingerprint__chunk">
        {chunk}
      </span>
    ));
}

function FingerprintField({ label, value, kind }) {
  return (
    <div className={`block-detail-fingerprint block-detail-fingerprint--${kind}`}>
      <span className="block-detail-fingerprint__label">{label}</span>
      <div className="block-detail-fingerprint__value" title={value || ''}>
        <FingerprintValue value={value} />
      </div>
    </div>
  );
}

export default function BlockDetailModal({ open, detail, loading, onClose }) {
  useEffect(() => {
    if (!open) return undefined;
    document.body.classList.add('modal-open');
    return () => {
      document.body.classList.remove('modal-open');
    };
  }, [open]);

  const modal = (
    <AnimatePresence initial={false}>
      {open ? (
        <motion.div
          className="block-detail-backdrop"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={onClose}
        >
          <motion.div
            className="block-detail-modal tech-panel"
            initial={{ opacity: 0, scale: 0.94, y: 24, filter: 'blur(8px)' }}
            animate={{ opacity: 1, scale: 1, y: 0, filter: 'blur(0px)' }}
            exit={{ opacity: 0, scale: 0.96, y: 16, filter: 'blur(6px)' }}
            transition={{ duration: 0.28, ease: [0.2, 0, 0, 1] }}
            onClick={(event) => event.stopPropagation()}
          >
            <div className="block-detail-modal__head">
              <div>
                <div className="dashboard-eyebrow">Fabric / Block Detail</div>
                <h3 className="block-detail-modal__title">
                  <Blocks size={18} />
                  {detail?.block_number != null ? `区块 #${detail.block_number}` : '区块详情'}
                </h3>
              </div>
              <button type="button" className="block-detail-close" onClick={onClose}>
                <X size={16} />
              </button>
            </div>

            {loading ? (
              <div className="block-detail-loading">正在加载区块详情...</div>
            ) : !detail ? (
              <div className="block-detail-loading">未找到区块详情</div>
            ) : (
              <div className="block-detail-body">
                <div className="block-detail-grid">
                  <div className="block-detail-metric">
                    <span>Batch ID</span>
                    <strong>{detail.batch_id || '—'}</strong>
                  </div>
                  <div className="block-detail-metric">
                    <span>批次 GOP 数</span>
                    <strong>{detail.event_count ?? detail.events?.length ?? 0}</strong>
                  </div>
                  <div className="block-detail-metric">
                    <span>区块时间</span>
                    <strong style={{ fontSize: '0.9rem' }}>{formatDateTime(detail.timestamp)}</strong>
                  </div>
                  <div className="block-detail-metric">
                    <span>链上状态</span>
                    <strong style={{ color: 'var(--nv-green)' }}>已锚定</strong>
                  </div>
                </div>

                <div className="block-detail-panel">
                  <div className="block-detail-panel__label">
                    <Hash size={13} />
                    Merkle Root
                  </div>
                  <CopyField value={detail.merkle_root} />
                </div>

                <div className="block-detail-panel">
                  <div className="block-detail-panel__label">
                    <Link2 size={13} />
                    TX ID
                  </div>
                  <CopyField value={detail.tx_id} />
                </div>

                <div className="block-detail-panel">
                  <div className="block-detail-panel__label">
                    <Layers size={13} />
                    区块内 GOP 摘要
                  </div>
                  <div className="block-detail-events">
                    {(detail.events || []).slice(0, 8).map((event, index) => (
                      <div key={event.event_id || `${event.evidence_hash}-${index}`} className="block-detail-eventRow">
                        <div className="block-detail-eventRow__meta">
                          <span>{event.event_id || `gop-${index + 1}`}</span>
                          <span>
                            <Clock size={11} />
                            {formatDateTime(event.timestamp || detail.timestamp)}
                          </span>
                        </div>
                        <div className="block-detail-eventRow__fingerprints">
                          <FingerprintField
                            label="SHA-256"
                            value={event.evidence_hash || event.sha256_hash || ''}
                            kind="hash"
                          />
                          <FingerprintField
                            label="VIF 指纹"
                            value={event.vif || ''}
                            kind="vif"
                          />
                        </div>
                      </div>
                    ))}
                    {(detail.events || []).length === 0 ? (
                      <div className="block-detail-empty">该区块暂无可展示 GOP 摘要</div>
                    ) : null}
                  </div>
                </div>
              </div>
            )}
          </motion.div>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );

  if (typeof document === 'undefined') return null;
  return createPortal(modal, document.body);
}
