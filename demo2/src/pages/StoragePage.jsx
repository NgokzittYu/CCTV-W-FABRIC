import { useState } from 'react';
import {
  HardDrive, Upload, Download, Pin, CheckCircle,
  Server, ArrowRight, Database, FileJson
} from 'lucide-react';
import GlassCard from '../components/GlassCard';
import { ipfsNodes, ipfsCIDExamples, storageComparison } from '../data/mockData';

export default function StoragePage() {
  const [uploadState, setUploadState] = useState('idle'); // idle, uploading, done
  const [uploadProgress, setUploadProgress] = useState(0);

  const simulateUpload = () => {
    setUploadState('uploading');
    setUploadProgress(0);
    const interval = setInterval(() => {
      setUploadProgress(p => {
        if (p >= 100) {
          clearInterval(interval);
          setUploadState('done');
          return 100;
        }
        return p + 4;
      });
    }, 50);
  };

  return (
    <div className="page-container">
      <div className="section-header">
        <h2 className="section-title"><HardDrive size={24} className="text-blue" /> IPFS 去中心化存储</h2>
        <p className="section-subtitle">CIDv1 内容寻址存储 — CID = SHA-256 multihash = 完整性证明</p>
      </div>

      {/* CID Principle */}
      <GlassCard className="cid-principle" glowColor="#3B82F6">
        <h4>内容寻址原理</h4>
        <div className="cid-flow">
          {[
            { label: 'GOP 原始字节', icon: '📦', color: '#8B5CF6' },
            { label: 'SHA-256 哈希', icon: '🔐', color: '#F59E0B' },
            { label: 'Multihash 编码', icon: '🧬', color: '#3B82F6' },
            { label: 'CIDv1', icon: '🔗', color: '#22C55E' },
          ].map((step, i) => (
            <div key={i} className="cid-step animate-fade-in-up" style={{ animationDelay: `${i * 80}ms` }}>
              <div className="cid-icon" style={{ background: `${step.color}15` }}>
                <span style={{ fontSize: '1.4rem' }}>{step.icon}</span>
              </div>
              <span className="cid-label">{step.label}</span>
              {i < 3 && <ArrowRight size={16} className="cid-arrow text-muted" />}
            </div>
          ))}
        </div>
        <div className="cid-example">
          <code>bafkreig5xdj7jkm4l2qn3v8y9w6r1t0p...qmzpw</code>
          <span className="text-muted" style={{ fontSize: '0.75rem' }}>CID 本身即为内容完整性证明，无需额外校验</span>
        </div>
      </GlassCard>

      {/* Cluster Status */}
      <section className="section">
        <h3 style={{ marginBottom: 16, display: 'flex', alignItems: 'center', gap: 10 }}>
          <Server size={18} className="text-cyan" /> IPFS Kubo 集群 (3 节点)
        </h3>
        <div className="grid-3">
          {ipfsNodes.map((node, i) => (
            <GlassCard
              key={node.id}
              glowColor="#06B6D4"
              className={`node-card animate-fade-in-up stagger-${i + 1}`}
            >
              <div className="node-header">
                <span className="node-name">{node.id}</span>
                <span className="node-status">
                  <span className="status-dot online" /> {node.status}
                </span>
              </div>
              <div className="node-details">
                <div className="node-detail">
                  <span className="text-muted">Peer ID</span>
                  <code>{node.peerId}</code>
                </div>
                <div className="node-detail">
                  <span className="text-muted">API Port</span>
                  <span>{node.port}</span>
                </div>
                <div className="node-detail">
                  <span className="text-muted">Objects</span>
                  <span>{node.objects}</span>
                </div>
                <div className="node-detail">
                  <span className="text-muted">Repo Size</span>
                  <span>{node.repoSize}</span>
                </div>
              </div>
            </GlassCard>
          ))}
        </div>
      </section>

      {/* Upload Simulation */}
      <section className="section">
        <h3 style={{ marginBottom: 16, display: 'flex', alignItems: 'center', gap: 10 }}>
          <Upload size={18} className="text-green" /> 模拟上传
        </h3>
        <GlassCard hover={false}>
          <div className="upload-panel">
            <button
              className="btn btn-primary"
              onClick={simulateUpload}
              disabled={uploadState === 'uploading'}
            >
              {uploadState === 'uploading' ? (
                <>上传中 {uploadProgress}%</>
              ) : uploadState === 'done' ? (
                <><CheckCircle size={16} /> 上传完成</>
              ) : (
                <><Upload size={16} /> 上传 GOP 到 IPFS</>
              )}
            </button>

            {uploadState !== 'idle' && (
              <div className="upload-progress-bar">
                <div
                  className="upload-fill"
                  style={{
                    width: `${uploadProgress}%`,
                    background: uploadState === 'done' ? 'var(--accent-green)' : 'var(--accent-blue)',
                  }}
                />
              </div>
            )}

            {uploadState === 'done' && (
              <div className="upload-result animate-fade-in-up">
                {ipfsCIDExamples.map((item, i) => (
                  <div key={i} className="cid-row">
                    <div className="cid-type" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                      {item.type === 'GOP 视频分片' ? <HardDrive size={14} /> :
                       item.type === '语义 JSON' ? <FileJson size={14} /> :
                       <Database size={14} />}
                      {item.type}
                    </div>
                    <code className="cid-hash">{item.cid}</code>
                    <span className="cid-size">{item.size}</span>
                    <span className="cid-pin">
                      <Pin size={12} /> Pinned
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </GlassCard>
      </section>

      {/* MinIO vs IPFS */}
      <section className="section">
        <h3 style={{ marginBottom: 16, display: 'flex', alignItems: 'center', gap: 10 }}>
          <Database size={18} className="text-amber" /> 存储方案对比
        </h3>
        <GlassCard hover={false}>
          <div className="table-wrapper">
            <table>
              <thead>
                <tr>
                  <th>特性</th>
                  <th style={{ color: 'var(--text-muted)' }}>MinIO (旧)</th>
                  <th style={{ color: 'var(--accent-green)' }}>IPFS (新)</th>
                </tr>
              </thead>
              <tbody>
                {storageComparison.map((row, i) => (
                  <tr key={i}>
                    <td style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{row.feature}</td>
                    <td style={{ color: 'var(--text-muted)' }}>{row.minio}</td>
                    <td style={{ color: 'var(--accent-green)' }}>{row.ipfs}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </GlassCard>
      </section>

      <style>{`
        .cid-principle { margin-bottom: 32px; }
        .cid-flow {
          display: flex;
          align-items: center;
          gap: 8px;
          margin: 20px 0;
          flex-wrap: wrap;
          justify-content: center;
        }
        .cid-step {
          display: flex;
          align-items: center;
          gap: 8px;
        }
        .cid-icon {
          width: 56px;
          height: 56px;
          border-radius: 14px;
          display: flex;
          align-items: center;
          justify-content: center;
        }
        .cid-label {
          font-size: 0.8rem;
          font-weight: 500;
        }
        .cid-arrow { margin: 0 4px; }
        .cid-example {
          display: flex;
          flex-direction: column;
          gap: 4px;
          padding: 12px 16px;
          border-radius: 8px;
          background: var(--bg-secondary);
          margin-top: 8px;
        }
        .cid-example code {
          color: var(--accent-blue);
          word-break: break-all;
        }
        .node-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 12px;
        }
        .node-name {
          font-weight: 600;
          font-size: 0.9rem;
        }
        .node-status {
          display: flex;
          align-items: center;
          gap: 6px;
          font-size: 0.75rem;
          color: var(--accent-green);
        }
        .status-dot {
          width: 8px;
          height: 8px;
          border-radius: 50%;
          animation: pulse-glow 2s ease infinite;
        }
        .status-dot.online { background: var(--accent-green); }
        .node-details {
          display: flex;
          flex-direction: column;
          gap: 8px;
        }
        .node-detail {
          display: flex;
          justify-content: space-between;
          font-size: 0.8rem;
        }
        .node-detail code {
          color: var(--text-secondary);
          font-size: 0.75rem;
        }
        .upload-panel {
          display: flex;
          flex-direction: column;
          gap: 16px;
        }
        .upload-progress-bar {
          height: 6px;
          border-radius: 3px;
          background: var(--bg-secondary);
          overflow: hidden;
        }
        .upload-fill {
          height: 100%;
          border-radius: 3px;
          transition: width 50ms linear;
        }
        .upload-result {
          display: flex;
          flex-direction: column;
          gap: 10px;
        }
        .cid-row {
          display: flex;
          align-items: center;
          gap: 16px;
          padding: 10px 14px;
          border-radius: 8px;
          background: var(--bg-secondary);
          font-size: 0.8rem;
          flex-wrap: wrap;
        }
        .cid-type {
          min-width: 120px;
          font-weight: 500;
        }
        .cid-hash {
          flex: 1;
          color: var(--accent-blue);
          font-size: 0.75rem;
          min-width: 160px;
        }
        .cid-size {
          color: var(--text-muted);
          font-size: 0.75rem;
        }
        .cid-pin {
          display: flex;
          align-items: center;
          gap: 4px;
          color: var(--accent-green);
          font-size: 0.7rem;
        }
        .table-wrapper { overflow-x: auto; }
        table { width: 100%; border-collapse: collapse; font-size: 0.8rem; }
        th, td {
          padding: 12px 16px;
          text-align: left;
          border-bottom: 1px solid var(--border-color);
        }
        th {
          font-size: 0.7rem;
          text-transform: uppercase;
          letter-spacing: 0.05em;
          color: var(--text-muted);
        }
        td { color: var(--text-secondary); }
      `}</style>
    </div>
  );
}
