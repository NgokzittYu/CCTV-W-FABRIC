import { useState } from 'react';
import {
  Film, Cpu, Layers, Key, ChevronRight,
  Hash, Fingerprint, ScanEye, ArrowRight
} from 'lucide-react';
import GlassCard from '../components/GlassCard';
import StatusBadge from '../components/StatusBadge';
import { gopList, vifComparison, vifPipeline } from '../data/mockData';

export default function EdgePage() {
  const [selectedGop, setSelectedGop] = useState(null);
  const [activeTab, setActiveTab] = useState('gop');
  const [triStateDemo, setTriStateDemo] = useState(0);

  const iconMap = { Film, Cpu, Layers, Key };

  const triStates = [
    { state: 'INTACT', risk: 0.0, dist: 0, label: '原始 SHA-256 一致', color: '#22C55E' },
    { state: 'RE_ENCODED', risk: 0.18, dist: 46, label: 'Hamming 距离 < 0.35 阈值', color: '#F59E0B' },
    { state: 'TAMPERED', risk: 0.62, dist: 159, label: 'Hamming 距离 ≥ 0.35 阈值', color: '#EF4444' },
  ];

  return (
    <div className="page-container">
      {/* Tab Switcher */}
      <div className="tab-bar">
        {[
          { id: 'gop', label: 'GOP 切分与哈希' },
          { id: 'vif', label: 'VIF v4 指纹' },
          { id: 'detect', label: 'YOLO 检测 & EIS' },
        ].map(tab => (
          <button
            key={tab.id}
            className={`tab-btn ${activeTab === tab.id ? 'active' : ''}`}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* ──────── GOP Tab ──────── */}
      {activeTab === 'gop' && (
        <section className="section">
          <div className="section-header">
            <h2 className="section-title"><Film size={24} className="text-blue" /> GOP 级视频切分</h2>
            <p className="section-subtitle">按 Group of Pictures 切分视频流，计算三重哈希指纹</p>
          </div>

          <div className="gop-timeline">
            {gopList.map((gop, i) => (
              <div
                key={gop.gop_id}
                className={`gop-block ${selectedGop === i ? 'selected' : ''} ${gop.should_anchor ? 'anchored' : ''}`}
                onClick={() => setSelectedGop(selectedGop === i ? null : i)}
                style={{ animationDelay: `${i * 40}ms` }}
              >
                <div className="gop-id">GOP {gop.gop_id}</div>
                <div className="gop-frames">{gop.frame_count}帧</div>
                {gop.should_anchor && <div className="anchor-dot" />}
              </div>
            ))}
          </div>

          {selectedGop !== null && (
            <GlassCard glowColor="#3B82F6" className="gop-detail animate-fade-in-up">
              <h4>GOP {gopList[selectedGop].gop_id} 详情</h4>
              <div className="detail-grid">
                <div className="detail-item">
                  <Hash size={14} className="text-muted" />
                  <span className="detail-label">SHA-256</span>
                  <code className="detail-value">{gopList[selectedGop].sha256}</code>
                </div>
                <div className="detail-item">
                  <Fingerprint size={14} className="text-muted" />
                  <span className="detail-label">pHash</span>
                  <code className="detail-value">{gopList[selectedGop].phash}</code>
                </div>
                <div className="detail-item">
                  <ScanEye size={14} className="text-muted" />
                  <span className="detail-label">VIF v4</span>
                  <code className="detail-value">{gopList[selectedGop].vif}</code>
                </div>
                <div className="detail-item">
                  <Film size={14} className="text-muted" />
                  <span className="detail-label">时间范围</span>
                  <span className="detail-value">{gopList[selectedGop].start_time}s - {gopList[selectedGop].end_time}s</span>
                </div>
                <div className="detail-item">
                  <Layers size={14} className="text-muted" />
                  <span className="detail-label">大小</span>
                  <span className="detail-value">{(gopList[selectedGop].byte_size / 1024).toFixed(1)} KB</span>
                </div>
              </div>
            </GlassCard>
          )}
        </section>
      )}

      {/* ──────── VIF Tab ──────── */}
      {activeTab === 'vif' && (
        <section className="section">
          <div className="section-header">
            <h2 className="section-title"><Fingerprint size={24} className="text-purple" /> VIF v4 视觉完整性指纹</h2>
            <p className="section-subtitle">纯视觉 CNN Embedding + Mean Pooling 架构，支持三态判定</p>
          </div>

          {/* Pipeline */}
          <div className="pipeline">
            {vifPipeline.map((step, i) => {
              const Icon = iconMap[step.icon] || Cpu;
              return (
                <div key={step.step} className="pipeline-step animate-fade-in-up" style={{ animationDelay: `${i * 80}ms` }}>
                  <div className="pipeline-icon" style={{ background: `${step.color}20`, color: step.color }}>
                    <Icon size={20} />
                  </div>
                  <div className="pipeline-content">
                    <div className="pipeline-label" style={{ color: step.color }}>Step {step.step}</div>
                    <div className="pipeline-title">{step.label}</div>
                    <div className="pipeline-desc">{step.desc}</div>
                  </div>
                  {i < vifPipeline.length - 1 && (
                    <ArrowRight size={16} className="pipeline-arrow text-muted" />
                  )}
                </div>
              );
            })}
          </div>

          {/* Tri-State Demo */}
          <GlassCard glowColor={triStates[triStateDemo].color} className="tri-state-demo">
            <h4>三态判定演示</h4>
            <div className="tri-buttons">
              {triStates.map((s, i) => (
                <button
                  key={s.state}
                  className={`btn btn-sm ${triStateDemo === i ? 'active-tri' : 'btn-ghost'}`}
                  style={triStateDemo === i ? { background: `${s.color}20`, color: s.color, border: `1px solid ${s.color}50` } : {}}
                  onClick={() => setTriStateDemo(i)}
                >
                  {s.state}
                </button>
              ))}
            </div>
            <div className="tri-result">
              <div className="tri-gauge">
                <svg viewBox="0 0 200 120" width="200" height="120">
                  <path d="M 20 100 A 80 80 0 0 1 180 100" fill="none" stroke="var(--border-color)" strokeWidth="8" strokeLinecap="round" />
                  <path
                    d="M 20 100 A 80 80 0 0 1 180 100"
                    fill="none"
                    stroke={triStates[triStateDemo].color}
                    strokeWidth="8"
                    strokeLinecap="round"
                    strokeDasharray={`${triStates[triStateDemo].risk * 251} 251`}
                    style={{ transition: 'stroke-dasharray 600ms cubic-bezier(0.23, 1, 0.32, 1), stroke 300ms ease' }}
                  />
                  <text x="100" y="85" textAnchor="middle" fill={triStates[triStateDemo].color}
                    style={{ fontSize: '24px', fontFamily: 'var(--font-display)', fontWeight: 700 }}>
                    {triStates[triStateDemo].risk}
                  </text>
                  <text x="100" y="105" textAnchor="middle" fill="var(--text-muted)" style={{ fontSize: '10px' }}>
                    Risk Score
                  </text>
                </svg>
              </div>
              <div className="tri-info">
                <StatusBadge state={triStates[triStateDemo].state} />
                <p style={{ marginTop: 8, fontSize: '0.85rem' }}>
                  Hamming 距离: <strong>{triStates[triStateDemo].dist}</strong>/256
                  ({(triStates[triStateDemo].dist / 256).toFixed(3)})
                </p>
                <p style={{ fontSize: '0.8rem', marginTop: 4 }}>{triStates[triStateDemo].label}</p>
              </div>
            </div>
          </GlassCard>

          {/* Comparison Table */}
          <GlassCard className="comparison-table" hover={false}>
            <h4 style={{ marginBottom: 16 }}>VIF v4 vs 初代方案对比</h4>
            <div className="table-wrapper">
              <table>
                <thead>
                  <tr>
                    {vifComparison.columns.map((col, i) => (
                      <th key={i} style={i > 0 ? { color: i === 2 ? 'var(--accent-green)' : 'var(--text-muted)' } : {}}>{col}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {vifComparison.rows.map((row, i) => (
                    <tr key={i}>
                      {row.map((cell, j) => (
                        <td key={j} style={j === 0 ? { fontWeight: 600, color: 'var(--text-primary)' } : {}}>{cell}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </GlassCard>
        </section>
      )}

      {/* ──────── Detect Tab ──────── */}
      {activeTab === 'detect' && (
        <section className="section">
          <div className="section-header">
            <h2 className="section-title"><ScanEye size={24} className="text-cyan" /> YOLO 目标检测 & EIS 评分</h2>
            <p className="section-subtitle">实时语义提取，驱动 MAB 自适应锚定策略</p>
          </div>

          <div className="grid-2">
            <GlassCard glowColor="#06B6D4">
              <h4>检测结果统计</h4>
              <div className="detect-summary">
                {['person', 'car', 'bicycle'].map(cls => {
                  const total = gopList.reduce((sum, g) => sum + (g.detections.find(d => d.class === cls)?.count || 0), 0);
                  const max = cls === 'person' ? 60 : 30;
                  return (
                    <div key={cls} className="detect-bar-item">
                      <div className="detect-bar-label">
                        <span>{cls}</span>
                        <span className="text-muted">{total}</span>
                      </div>
                      <div className="detect-bar-track">
                        <div
                          className="detect-bar-fill"
                          style={{
                            width: `${(total / max) * 100}%`,
                            background: cls === 'person' ? '#8B5CF6' : cls === 'car' ? '#3B82F6' : '#22C55E',
                          }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            </GlassCard>

            <GlassCard glowColor="#F59E0B">
              <h4>EIS 评分分布</h4>
              <div className="eis-grid">
                {gopList.map(gop => (
                  <div key={gop.gop_id} className="eis-cell" title={`GOP ${gop.gop_id}: EIS=${gop.eis_score}`}>
                    <div
                      className="eis-bar"
                      style={{
                        height: `${gop.eis_score * 100}%`,
                        background: gop.eis_score > 0.7 ? '#EF4444' : gop.eis_score > 0.3 ? '#F59E0B' : '#22C55E',
                      }}
                    />
                    <span className="eis-label">{gop.gop_id}</span>
                  </div>
                ))}
              </div>
              <div className="eis-legend">
                <span><span className="legend-dot" style={{ background: '#22C55E' }} /> 低 (&lt;0.3)</span>
                <span><span className="legend-dot" style={{ background: '#F59E0B' }} /> 中 (0.3-0.7)</span>
                <span><span className="legend-dot" style={{ background: '#EF4444' }} /> 高 (&gt;0.7)</span>
              </div>
            </GlassCard>
          </div>
        </section>
      )}

      <style>{`
        .tab-bar {
          display: flex;
          gap: 4px;
          padding: 4px;
          background: var(--glass-bg);
          border-radius: 12px;
          border: 1px solid var(--glass-border);
          margin-bottom: 32px;
          width: fit-content;
        }
        .tab-btn {
          padding: 8px 20px;
          border: none;
          background: none;
          color: var(--text-muted);
          font-family: var(--font-body);
          font-size: 0.85rem;
          font-weight: 500;
          cursor: pointer;
          border-radius: 8px;
          transition: all 200ms ease;
        }
        .tab-btn:active { transform: scale(0.97); }
        .tab-btn.active {
          background: var(--accent-purple-dim);
          color: var(--accent-purple);
        }

        .gop-timeline {
          display: flex;
          gap: 12px;
          flex-wrap: wrap;
          margin-bottom: 32px;
        }
        .gop-block {
          position: relative;
          padding: 16px 20px;
          min-width: 90px;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          gap: 4px;
          border-radius: 12px;
          background: var(--bg-card);
          border: 1px solid var(--border-color);
          cursor: pointer;
          transition: transform 250ms cubic-bezier(0.34, 1.56, 0.64, 1), background 200ms ease, border-color 200ms ease, box-shadow 200ms ease;
          animation: fadeInUp 400ms var(--ease-out) forwards;
          opacity: 0;
        }
        .gop-block:hover { 
          border-color: var(--accent-blue);
          transform: translateY(-2px);
          box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
        }
        .gop-block:active {
          transform: scale(0.96) translateY(0);
        }
        .gop-block.selected {
          border-color: var(--accent-blue);
          background: var(--accent-blue-dim);
          box-shadow: var(--shadow-glow-blue);
          transform: translateY(-2px) scale(1.02);
        }
        .gop-block.anchored .anchor-dot {
          position: absolute;
          top: 8px;
          right: 8px;
          width: 8px;
          height: 8px;
          border-radius: 50%;
          background: var(--accent-green);
          box-shadow: 0 0 8px var(--accent-green);
        }
        .gop-id { font-size: 0.95rem; font-weight: 600; color: var(--text-primary); letter-spacing: 0.02em; }
        .gop-frames { font-size: 0.75rem; color: var(--text-muted); font-family: 'JetBrains Mono', monospace; }

        .gop-detail { margin-top: 16px; }
        .detail-grid {
          display: flex;
          flex-direction: column;
          gap: 12px;
          margin-top: 16px;
        }
        .detail-item {
          display: flex;
          align-items: center;
          gap: 10px;
          font-size: 0.85rem;
        }
        .detail-label {
          color: var(--text-muted);
          width: 80px;
          flex-shrink: 0;
        }
        .detail-value {
          font-family: 'JetBrains Mono', monospace;
          font-size: 0.78rem;
          color: var(--text-secondary);
          word-break: break-all;
        }

        .pipeline {
          display: flex;
          gap: 12px;
          margin-bottom: 32px;
          flex-wrap: wrap;
        }
        .pipeline-step {
          flex: 1;
          min-width: 200px;
          display: flex;
          flex-direction: column;
          align-items: center;
          text-align: center;
          position: relative;
          padding: 20px 16px;
          border-radius: 12px;
          background: var(--glass-bg);
          border: 1px solid var(--glass-border);
        }
        .pipeline-icon {
          width: 44px;
          height: 44px;
          border-radius: 12px;
          display: flex;
          align-items: center;
          justify-content: center;
          margin-bottom: 12px;
        }
        .pipeline-label {
          font-size: 0.65rem;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.06em;
        }
        .pipeline-title {
          font-weight: 600;
          font-size: 0.9rem;
          margin-top: 4px;
          color: var(--text-primary);
        }
        .pipeline-desc {
          font-size: 0.75rem;
          color: var(--text-muted);
          margin-top: 4px;
        }
        .pipeline-arrow {
          position: absolute;
          right: -14px;
          top: 50%;
          transform: translateY(-50%);
        }

        .tri-state-demo { margin-bottom: 24px; }
        .tri-buttons {
          display: flex;
          gap: 8px;
          margin: 16px 0;
        }
        .tri-result {
          display: flex;
          align-items: center;
          gap: 32px;
          margin-top: 16px;
        }
        .tri-info {
          flex: 1;
        }

        .table-wrapper { overflow-x: auto; }
        table {
          width: 100%;
          border-collapse: collapse;
          font-size: 0.8rem;
        }
        th, td {
          padding: 10px 14px;
          text-align: left;
          border-bottom: 1px solid var(--border-color);
        }
        th {
          font-size: 0.7rem;
          text-transform: uppercase;
          letter-spacing: 0.05em;
          color: var(--text-muted);
        }
        td {
          color: var(--text-secondary);
        }

        .detect-summary {
          display: flex;
          flex-direction: column;
          gap: 16px;
          margin-top: 16px;
        }
        .detect-bar-label {
          display: flex;
          justify-content: space-between;
          font-size: 0.8rem;
          margin-bottom: 4px;
        }
        .detect-bar-track {
          height: 8px;
          border-radius: 4px;
          background: var(--bg-secondary);
        }
        .detect-bar-fill {
          height: 100%;
          border-radius: 4px;
          transition: width 800ms var(--ease-out);
        }

        .eis-grid {
          display: flex;
          gap: 6px;
          align-items: flex-end;
          height: 120px;
          margin-top: 16px;
        }
        .eis-cell {
          flex: 1;
          display: flex;
          flex-direction: column;
          align-items: center;
          height: 100%;
          justify-content: flex-end;
        }
        .eis-bar {
          width: 100%;
          border-radius: 4px 4px 0 0;
          transition: height 600ms var(--ease-out);
          min-height: 4px;
        }
        .eis-label {
          font-size: 0.6rem;
          color: var(--text-muted);
          margin-top: 4px;
        }
        .eis-legend {
          display: flex;
          gap: 16px;
          margin-top: 12px;
          font-size: 0.7rem;
          color: var(--text-muted);
        }
        .legend-dot {
          display: inline-block;
          width: 8px;
          height: 8px;
          border-radius: 50%;
          margin-right: 4px;
        }
      `}</style>
    </div>
  );
}
