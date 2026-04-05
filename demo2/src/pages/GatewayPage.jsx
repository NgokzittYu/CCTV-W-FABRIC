import { useState, useEffect, useCallback } from 'react';
import {
  Network, Swords, Play, Pause, RotateCcw, TrendingUp,
  GitBranch, Binary, ChevronDown
} from 'lucide-react';
import GlassCard from '../components/GlassCard';
import { mabArms, generateMABSimulation, merkleTreeData } from '../data/mockData';

export default function GatewayPage() {
  const [activeTab, setActiveTab] = useState('mab');
  const [simData, setSimData] = useState([]);
  const [simStep, setSimStep] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [expandedChunk, setExpandedChunk] = useState(null);

  // Generate simulation data once
  useEffect(() => {
    setSimData(generateMABSimulation(100));
  }, []);

  // Auto-play simulation
  useEffect(() => {
    if (!isPlaying || simStep >= simData.length - 1) {
      if (simStep >= simData.length - 1) setIsPlaying(false);
      return;
    }
    const timer = setTimeout(() => setSimStep(s => s + 1), 80);
    return () => clearTimeout(timer);
  }, [isPlaying, simStep, simData.length]);

  const resetSim = useCallback(() => {
    setSimStep(0);
    setIsPlaying(false);
    setSimData(generateMABSimulation(100));
  }, []);

  const currentData = simData[simStep];
  const historySlice = simData.slice(0, simStep + 1);

  return (
    <div className="page-container">
      <div className="tab-bar">
        {[
          { id: 'mab', label: 'MAB 自适应锚定' },
          { id: 'merkle', label: '三级 Merkle 树' },
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

      {/* ──────── MAB Tab ──────── */}
      {activeTab === 'mab' && (
        <section className="section">
          <div className="section-header">
            <h2 className="section-title"><Swords size={24} className="text-red" /> MAB 自适应锚定引擎</h2>
            <p className="section-subtitle">UCB1 强化学习策略，动态调节上链频率，降低 95% 成本</p>
          </div>

          {/* Arms display */}
          <div className="grid-4" style={{ marginBottom: 24 }}>
            {mabArms.map((arm) => (
              <GlassCard
                key={arm.arm}
                glowColor={arm.color}
                className={`arm-card ${currentData?.arm === arm.arm ? 'arm-active' : ''}`}
              >
                <div className="arm-header">
                  <span className="arm-id" style={{ color: arm.color }}>Arm {arm.arm}</span>
                  {currentData?.arm === arm.arm && <span className="arm-selected">当前选择</span>}
                </div>
                <div className="arm-interval">{arm.label}</div>
                <div className="arm-desc">{arm.desc}</div>
                {currentData && (
                  <div className="arm-count">
                    被选次数: <strong>{currentData.armCounts[arm.arm]}</strong>
                  </div>
                )}
              </GlassCard>
            ))}
          </div>

          {/* Simulation controls */}
          <GlassCard hover={false} className="sim-panel">
            <div className="sim-controls">
              <button className="btn btn-primary btn-sm" onClick={() => setIsPlaying(!isPlaying)}>
                {isPlaying ? <Pause size={14} /> : <Play size={14} />}
                {isPlaying ? '暂停' : '运行模拟'}
              </button>
              <button className="btn btn-ghost btn-sm" onClick={resetSim}>
                <RotateCcw size={14} /> 重置
              </button>
              <div className="sim-progress">
                <span className="text-muted" style={{ fontSize: '0.8rem' }}>Step {simStep + 1}/100</span>
                <div className="progress-track">
                  <div className="progress-fill" style={{ width: `${((simStep + 1) / 100) * 100}%` }} />
                </div>
              </div>
              {currentData && (
                <div className="sim-stats">
                  <span className="stat-chip">
                    场景: <strong style={{ color: currentData.isActive ? '#EF4444' : '#22C55E' }}>
                      {currentData.isActive ? '活跃' : '平静'}
                    </strong>
                  </span>
                  <span className="stat-chip">
                    累计 Reward: <strong className="text-purple">{currentData.cumulativeReward}</strong>
                  </span>
                </div>
              )}
            </div>

            {/* Reward Chart */}
            <div className="reward-chart">
              <svg viewBox={`0 0 800 200`} width="100%" height="200" preserveAspectRatio="none">
                {/* Grid lines */}
                {[0, 0.25, 0.5, 0.75, 1].map(y => (
                  <line key={y} x1="0" y1={200 - y * 200} x2="800" y2={200 - y * 200}
                    stroke="var(--border-color)" strokeWidth="0.5" />
                ))}
                {/* Cumulative reward line */}
                {historySlice.length > 1 && (
                  <polyline
                    fill="none"
                    stroke="var(--accent-purple)"
                    strokeWidth="2"
                    points={historySlice.map((d, i) => {
                      const x = (i / 99) * 800;
                      const maxR = Math.max(...simData.map(s => s.cumulativeReward), 1);
                      const y = 200 - (d.cumulativeReward / maxR) * 180 - 10;
                      return `${x},${y}`;
                    }).join(' ')}
                  />
                )}
                {/* Arm selection dots */}
                {historySlice.map((d, i) => {
                  const x = (i / 99) * 800;
                  return (
                    <circle key={i} cx={x} cy={195} r="2.5"
                      fill={mabArms[d.arm].color} opacity={0.8} />
                  );
                })}
                {/* Scene indicator */}
                {historySlice.map((d, i) => {
                  const x = (i / 99) * 800;
                  return (
                    <rect key={`bg-${i}`} x={x} y="0" width={800 / 100} height="4"
                      fill={d.isActive ? 'rgba(239,68,68,0.3)' : 'rgba(34,197,94,0.15)'} />
                  );
                })}
              </svg>
              <div className="chart-labels">
                <span className="text-muted" style={{ fontSize: '0.65rem' }}>步骤 0</span>
                <span className="text-muted" style={{ fontSize: '0.65rem' }}>累计 Reward 曲线</span>
                <span className="text-muted" style={{ fontSize: '0.65rem' }}>步骤 100</span>
              </div>
            </div>
          </GlassCard>
        </section>
      )}

      {/* ──────── Merkle Tab ──────── */}
      {activeTab === 'merkle' && (
        <section className="section">
          <div className="section-header">
            <h2 className="section-title"><GitBranch size={24} className="text-green" /> 三级 Merkle 树</h2>
            <p className="section-subtitle">GOP → Chunk(30s) → Segment(5min) 层级结构，支持精确篡改定位</p>
          </div>

          {/* Tree visualization */}
          <GlassCard hover={false} className="merkle-viz">
            {/* Root */}
            <div className="merkle-level">
              <div className="merkle-label">Segment Root</div>
              <div className="merkle-node root-node">
                <Binary size={14} />
                <code>{merkleTreeData.segmentRoot}</code>
              </div>
            </div>

            <div className="merkle-connector">
              <svg width="100%" height="30">
                <line x1="50%" y1="0" x2="25%" y2="30" stroke="var(--accent-purple)" strokeWidth="1.5" strokeDasharray="4 2" />
                <line x1="50%" y1="0" x2="75%" y2="30" stroke="var(--accent-purple)" strokeWidth="1.5" strokeDasharray="4 2" />
              </svg>
            </div>

            {/* Chunks */}
            <div className="merkle-level">
              <div className="merkle-label">Chunk Roots (30s)</div>
              <div className="merkle-chunks">
                {merkleTreeData.chunks.map((chunk, i) => (
                  <div key={i} className="chunk-group">
                    <div
                      className={`merkle-node chunk-node ${expandedChunk === i ? 'expanded' : ''}`}
                      onClick={() => setExpandedChunk(expandedChunk === i ? null : i)}
                    >
                      <code>{chunk.chunkRoot}</code>
                      <span className="chunk-time">{chunk.timeRange}</span>
                      <ChevronDown
                        size={14}
                        style={{
                          transition: 'transform 200ms ease',
                          transform: expandedChunk === i ? 'rotate(180deg)' : 'rotate(0)',
                        }}
                      />
                    </div>

                    {expandedChunk === i && (
                      <div className="chunk-gops animate-fade-in-up">
                        <svg width="100%" height="20">
                          {chunk.gops.map((_, j) => (
                            <line
                              key={j}
                              x1="50%"
                              y1="0"
                              x2={`${((j + 0.5) / chunk.gops.length) * 100}%`}
                              y2="20"
                              stroke="var(--accent-blue)"
                              strokeWidth="1"
                              strokeDasharray="3 2"
                            />
                          ))}
                        </svg>
                        <div className="gop-leaves">
                          {chunk.gops.map((gop, j) => (
                            <div
                              key={j}
                              className="merkle-node leaf-node"
                              style={{ animationDelay: `${j * 50}ms` }}
                            >
                              <span className="leaf-id">GOP {gop.gopId}</span>
                              <code>{gop.leafHash}</code>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          </GlassCard>

          {/* Merkle Proof explainer */}
          <GlassCard glowColor="#3B82F6">
            <h4>Merkle Proof 验证原理</h4>
            <div className="proof-steps">
              {[
                '从叶子哈希 (GOP Leaf) 出发',
                '逐层与兄弟节点哈希拼接计算 SHA-256',
                '最终计算得到 Root Hash',
                '与链上锚定的 SegmentRoot 对比',
                '一致则验证通过 (INTACT)',
              ].map((step, i) => (
                <div key={i} className="proof-step" style={{ animationDelay: `${i * 60}ms` }}>
                  <span className="step-num" style={{ background: i === 4 ? 'var(--accent-green-dim)' : 'var(--accent-blue-dim)', color: i === 4 ? 'var(--accent-green)' : 'var(--accent-blue)' }}>
                    {i + 1}
                  </span>
                  <span>{step}</span>
                </div>
              ))}
            </div>
          </GlassCard>
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
        .arm-card {
          transition: all 200ms ease;
        }
        .arm-card.arm-active {
          border-color: var(--accent-purple) !important;
          box-shadow: 0 0 20px rgba(139, 92, 246, 0.3) !important;
        }
        .arm-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
        }
        .arm-id {
          font-family: var(--font-display);
          font-size: 0.75rem;
          font-weight: 600;
        }
        .arm-selected {
          font-size: 0.6rem;
          padding: 2px 8px;
          border-radius: 10px;
          background: var(--accent-green-dim);
          color: var(--accent-green);
        }
        .arm-interval {
          font-size: 1rem;
          font-weight: 600;
          margin-top: 8px;
        }
        .arm-desc {
          font-size: 0.75rem;
          color: var(--text-muted);
          margin-top: 2px;
        }
        .arm-count {
          font-size: 0.75rem;
          color: var(--text-secondary);
          margin-top: 8px;
          padding-top: 8px;
          border-top: 1px solid var(--border-color);
        }
        .sim-panel { margin-bottom: 24px; }
        .sim-controls {
          display: flex;
          gap: 12px;
          align-items: center;
          flex-wrap: wrap;
        }
        .sim-progress {
          flex: 1;
          min-width: 120px;
        }
        .progress-track {
          height: 4px;
          border-radius: 2px;
          background: var(--bg-secondary);
          margin-top: 4px;
        }
        .progress-fill {
          height: 100%;
          border-radius: 2px;
          background: var(--accent-purple);
          transition: width 80ms linear;
        }
        .sim-stats {
          display: flex;
          gap: 12px;
        }
        .stat-chip {
          font-size: 0.75rem;
          padding: 4px 10px;
          border-radius: 8px;
          background: var(--bg-card);
          color: var(--text-secondary);
        }
        .reward-chart {
          margin-top: 20px;
          border-radius: 8px;
          overflow: hidden;
          background: var(--bg-secondary);
          padding: 8px;
        }
        .chart-labels {
          display: flex;
          justify-content: space-between;
          padding: 4px 8px;
        }
        .merkle-viz { padding: 32px; }
        .merkle-level {
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: 12px;
        }
        .merkle-label {
          font-size: 0.7rem;
          color: var(--text-muted);
          text-transform: uppercase;
          letter-spacing: 0.06em;
        }
        .merkle-node {
          display: flex;
          align-items: center;
          gap: 8px;
          padding: 8px 16px;
          border-radius: 8px;
          font-size: 0.8rem;
        }
        .merkle-node code {
          color: var(--text-secondary);
          font-size: 0.75rem;
        }
        .root-node {
          background: var(--accent-purple-dim);
          border: 1px solid rgba(139, 92, 246, 0.3);
          color: var(--accent-purple);
        }
        .merkle-connector {
          display: flex;
          justify-content: center;
        }
        .merkle-chunks {
          display: flex;
          gap: 24px;
          width: 100%;
          justify-content: center;
          flex-wrap: wrap;
        }
        .chunk-group {
          min-width: 200px;
          display: flex;
          flex-direction: column;
          align-items: center;
        }
        .chunk-node {
          background: var(--accent-green-dim);
          border: 1px solid rgba(34, 197, 94, 0.3);
          cursor: pointer;
          flex-direction: column;
          transition: all 200ms ease;
        }
        .chunk-node:hover {
          border-color: var(--accent-green);
        }
        .chunk-time {
          font-size: 0.65rem;
          color: var(--text-muted);
        }
        .chunk-gops {
          margin-top: 8px;
          width: 100%;
        }
        .gop-leaves {
          display: flex;
          gap: 6px;
          flex-wrap: wrap;
          justify-content: center;
        }
        .leaf-node {
          background: var(--accent-blue-dim);
          border: 1px solid rgba(59, 130, 246, 0.2);
          flex-direction: column;
          font-size: 0.7rem;
          padding: 6px 10px;
          animation: fadeInUp 300ms var(--ease-out) forwards;
          opacity: 0;
        }
        .leaf-id {
          font-size: 0.6rem;
          font-weight: 600;
          color: var(--accent-blue);
        }
        .proof-steps {
          display: flex;
          flex-direction: column;
          gap: 12px;
          margin-top: 16px;
        }
        .proof-step {
          display: flex;
          align-items: center;
          gap: 12px;
          font-size: 0.85rem;
          color: var(--text-secondary);
          animation: fadeInUp 400ms var(--ease-out) forwards;
          opacity: 0;
        }
        .step-num {
          width: 28px;
          height: 28px;
          border-radius: 50%;
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 0.75rem;
          font-weight: 700;
          flex-shrink: 0;
        }
      `}</style>
    </div>
  );
}
