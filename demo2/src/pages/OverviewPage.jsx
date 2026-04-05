import { useState } from 'react';
import {
  Brain, Network, HardDrive, Link, Shield, Zap,
  ChevronRight, ArrowDown, Timer, Target, TrendingDown
} from 'lucide-react';
import GlassCard from '../components/GlassCard';
import AnimatedCounter from '../components/AnimatedCounter';
import { systemStats, techStack, architectureLayers } from '../data/mockData';

export default function OverviewPage() {
  const [expandedLayer, setExpandedLayer] = useState(null);

  const iconMap = { Brain, Network, HardDrive, Link };

  return (
    <div className="page-container">
      {/* Hero Section */}
      <section className="hero-section">
        <div className="hero-badge animate-fade-in-up stagger-1">
          <Shield size={14} />
          基于边缘 AI 与联盟链的监控视频防篡改系统
        </div>
        <h1 className="hero-title animate-fade-in-up stagger-2">
          Secure<span className="text-green">Lens</span>
        </h1>
        <p className="hero-subtitle animate-fade-in-up stagger-3">
          结合边缘 AI 智能分析与区块链不可篡改特性，实现司法级视频取证
        </p>

        <div className="stats-grid animate-fade-in-up stagger-4">
          <div className="stat-card">
            <div className="stat-value text-green"><AnimatedCounter value={systemStats.costReduction} suffix="%" /></div>
            <div className="stat-label">链上存储成本降低</div>
          </div>
          <div className="stat-card">
            <div className="stat-value text-purple"><AnimatedCounter value={systemStats.localizationPrecision} suffix="s" /></div>
            <div className="stat-label">篡改定位精度</div>
          </div>
          <div className="stat-card">
            <div className="stat-value text-blue"><AnimatedCounter value={systemStats.gopProcessingSpeed} suffix="/s" /></div>
            <div className="stat-label">GOP 处理速度</div>
          </div>
          <div className="stat-card">
            <div className="stat-value text-amber"><AnimatedCounter value={systemStats.vifComputeTime} suffix="ms" decimals={1} /></div>
            <div className="stat-label">VIF 计算延迟</div>
          </div>
        </div>
      </section>

      {/* Architecture Section */}
      <section className="section">
        <div className="section-header">
          <h2 className="section-title"><Zap size={24} className="text-purple" /> 四层核心架构</h2>
          <p className="section-subtitle">从边缘采集到链上存证的完整数据信任链路</p>
        </div>

        <div className="arch-flow">
          {architectureLayers.map((layer, i) => {
            const Icon = iconMap[layer.icon] || Brain;
            const isExpanded = expandedLayer === layer.id;
            return (
              <div key={layer.id}>
                <GlassCard
                  glowColor={layer.color}
                  onClick={() => setExpandedLayer(isExpanded ? null : layer.id)}
                  className="arch-card"
                >
                  <div className="arch-header">
                    <div className="arch-icon" style={{ background: `${layer.color}20`, color: layer.color }}>
                      <Icon size={24} />
                    </div>
                    <div className="arch-info">
                      <h3 style={{ color: layer.color }}>{layer.name}</h3>
                      <span className="text-muted" style={{ fontSize: '0.75rem' }}>{layer.nameEn}</span>
                    </div>
                    <ChevronRight
                      size={18}
                      className="text-muted"
                      style={{
                        transition: 'transform 200ms ease',
                        transform: isExpanded ? 'rotate(90deg)' : 'rotate(0)',
                      }}
                    />
                  </div>
                  <p style={{ fontSize: '0.85rem', marginTop: 8 }}>{layer.desc}</p>

                  {isExpanded && (
                    <ul className="arch-details">
                      {layer.details.map((d, j) => (
                        <li
                          key={j}
                          className="animate-fade-in-up"
                          style={{ animationDelay: `${j * 50}ms` }}
                        >
                          <span className="detail-dot" style={{ background: layer.color }} />
                          {d}
                        </li>
                      ))}
                    </ul>
                  )}
                </GlassCard>
                {i < architectureLayers.length - 1 && (
                  <div className="flow-arrow">
                    <ArrowDown size={20} className="text-muted" />
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </section>

      {/* Tech Stack */}
      <section className="section">
        <div className="section-header">
          <h2 className="section-title"><Target size={24} className="text-blue" /> 核心技术栈</h2>
        </div>
        <div className="grid-3">
          {techStack.map((tech, i) => (
            <GlassCard
              key={tech.name}
              glowColor={tech.color}
              className={`animate-fade-in-up stagger-${i + 1}`}
            >
              <div className="tech-header">
                <span className="tech-dot" style={{ background: tech.color }} />
                <span className="tech-category" style={{ color: tech.color }}>{tech.category}</span>
              </div>
              <h4 style={{ marginTop: 8 }}>{tech.name}</h4>
              <p style={{ fontSize: '0.8rem', marginTop: 6 }}>{tech.desc}</p>
            </GlassCard>
          ))}
        </div>
      </section>

      <style>{`
        .hero-section {
          text-align: center;
          padding: 60px 0 48px;
        }
        .hero-badge {
          display: inline-flex;
          align-items: center;
          gap: 8px;
          padding: 6px 16px;
          border-radius: 20px;
          font-size: 0.8rem;
          color: var(--accent-green);
          background: var(--accent-green-dim);
          border: 1px solid rgba(34, 197, 94, 0.3);
          margin-bottom: 24px;
        }
        .hero-title {
          font-size: 3.5rem;
          font-weight: 700;
          letter-spacing: 0.08em;
          margin-bottom: 16px;
        }
        .hero-subtitle {
          font-size: 1.1rem;
          color: var(--text-secondary);
          max-width: 600px;
          margin: 0 auto 40px;
        }
        .stats-grid {
          display: grid;
          grid-template-columns: repeat(4, 1fr);
          gap: 16px;
          max-width: 800px;
          margin: 0 auto;
        }
        .stat-card {
          padding: 20px;
          border-radius: 12px;
          background: var(--glass-bg);
          border: 1px solid var(--glass-border);
          text-align: center;
        }
        .stat-value {
          font-size: 1.8rem;
          font-weight: 700;
        }
        .stat-label {
          font-size: 0.75rem;
          color: var(--text-muted);
          margin-top: 4px;
        }
        .arch-flow {
          max-width: 640px;
          margin: 0 auto;
        }
        .arch-card {
          width: 100%;
        }
        .arch-header {
          display: flex;
          align-items: center;
          gap: 14px;
        }
        .arch-icon {
          width: 48px;
          height: 48px;
          border-radius: 12px;
          display: flex;
          align-items: center;
          justify-content: center;
          flex-shrink: 0;
        }
        .arch-info {
          flex: 1;
        }
        .arch-info h3 {
          font-size: 1rem;
        }
        .arch-details {
          list-style: none;
          margin-top: 16px;
          padding-top: 16px;
          border-top: 1px solid var(--border-color);
          display: flex;
          flex-direction: column;
          gap: 8px;
        }
        .arch-details li {
          display: flex;
          align-items: center;
          gap: 10px;
          font-size: 0.85rem;
          color: var(--text-secondary);
        }
        .detail-dot {
          width: 6px;
          height: 6px;
          border-radius: 50%;
          flex-shrink: 0;
        }
        .flow-arrow {
          display: flex;
          justify-content: center;
          padding: 8px 0;
          opacity: 0.4;
        }
        .tech-header {
          display: flex;
          align-items: center;
          gap: 8px;
        }
        .tech-dot {
          width: 8px;
          height: 8px;
          border-radius: 50%;
        }
        .tech-category {
          font-size: 0.7rem;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.06em;
        }
        @media (max-width: 768px) {
          .hero-title { font-size: 2.5rem; }
          .stats-grid { grid-template-columns: repeat(2, 1fr); }
        }
      `}</style>
    </div>
  );
}
