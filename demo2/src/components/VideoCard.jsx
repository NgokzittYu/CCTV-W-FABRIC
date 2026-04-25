import { Video, ShieldCheck, Clock, Layers, FileCode2 } from 'lucide-react';
import { motion } from 'framer-motion';

export default function VideoCard({ video, index = 0, onViewCert }) {
  const createdAt = video.created_at
    ? new Date(video.created_at * 1000).toLocaleString('zh-CN', { hour12: false })
    : '无数据';

  const fileSizeMB = video.file_size
    ? (video.file_size / (1024 * 1024)).toFixed(2) + 'MB'
    : '0.00MB';

  return (
    <motion.div
      className="tech-panel"
      initial={{ opacity: 0, scale: 0.98 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.15, delay: index * 0.05, ease: [0.2, 0, 0, 1] }}
      style={{ padding: '16px', display: 'flex', flexDirection: 'column', gap: '12px', height: '100%' }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span className="tag tag-nv"><ShieldCheck size={12}/> 已锚定</span>
        <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>{fileSizeMB}</span>
      </div>

      <h3 style={{ margin: 0, wordBreak: 'break-all', fontSize: '1rem' }} title={video.filename}>
        {video.filename}
      </h3>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', fontSize: '0.8rem', color: 'var(--text-muted)', flex: 1 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
          <span><Layers size={12} style={{ verticalAlign: 'middle', marginBottom: '2px' }}/> GOP 数量</span>
          <span style={{ color: 'var(--text-pure)' }}>{video.gop_count}</span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
          <span><Clock size={12} style={{ verticalAlign: 'middle', marginBottom: '2px' }}/> 记录时间</span>
          <span style={{ color: 'var(--text-pure)' }}>{createdAt}</span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
          <span>识别码</span>
          <span style={{ color: 'var(--text-pure)' }}>{video.id.split('-')[0]}...</span>
        </div>
        {video.block_number != null && (
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <span>区块高度</span>
            <span style={{ color: 'var(--nv-green)' }}>#{video.block_number}</span>
          </div>
        )}
      </div>

      <button
        className="btn btn-ghost"
        style={{ marginTop: '12px', border: '1px solid var(--border-subtle)', width: '100%' }}
        onClick={() => onViewCert && onViewCert(video.id)}
      >
        <FileCode2 size={14} /> 查看证书
      </button>
    </motion.div>
  );
}
