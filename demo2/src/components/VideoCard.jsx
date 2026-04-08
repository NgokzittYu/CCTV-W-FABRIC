import { Video, ShieldCheck, Clock, Layers, Eye } from 'lucide-react';
import { motion } from 'framer-motion';

/**
 * Card displaying a single archived video with quick actions.
 */
export default function VideoCard({ video, index = 0, onViewCert }) {
  const createdAt = video.created_at
    ? new Date(video.created_at * 1000).toLocaleString('zh-CN')
    : '—';

  const fileSizeMB = video.file_size
    ? (video.file_size / (1024 * 1024)).toFixed(2) + ' MB'
    : '—';

  return (
    <motion.div
      className="video-card glass-card"
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{
        duration: 0.4,
        delay: index * 0.06,
        ease: [0.23, 1, 0.32, 1],
      }}
    >
      {/* Thumbnail placeholder */}
      <div className="video-card-thumb">
        <Video size={24} />
        <div className="video-card-thumb-overlay">
          <span className="video-card-status badge-intact">
            <ShieldCheck size={10} /> 已存证
          </span>
        </div>
      </div>

      {/* Info */}
      <div className="video-card-info">
        <h4 className="video-card-name" title={video.filename}>
          {video.filename}
        </h4>

        <div className="video-card-meta">
          <span>
            <Layers size={12} /> {video.gop_count} GOPs
          </span>
          <span>
            <Clock size={12} /> {createdAt}
          </span>
        </div>

        <div className="video-card-meta">
          <span className="mono" style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>
            ID: {video.id}
          </span>
        </div>

        <div className="video-card-meta">
          <span style={{ fontSize: '0.7rem' }}>{fileSizeMB}</span>
          {video.block_number != null && (
            <span style={{ fontSize: '0.7rem' }}>Block #{video.block_number}</span>
          )}
        </div>
      </div>

      {/* Actions */}
      <div className="video-card-actions">
        <button
          className="btn btn-sm btn-secondary"
          onClick={() => onViewCert && onViewCert(video.id)}
        >
          <Eye size={13} /> 查看证书
        </button>
      </div>
    </motion.div>
  );
}
