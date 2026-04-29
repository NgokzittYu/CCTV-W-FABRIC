import { useEffect, useState } from 'react';
import {
  ArrowRight,
  BarChart3,
  Brain,
  Gauge,
  RadioTower,
  RefreshCw,
  Route,
  ShieldCheck,
  Timer,
  Zap,
} from 'lucide-react';
import { getAnchorStats } from '../services/api';

const LEVEL_COLORS = { LOW: '#22c55e', MEDIUM: '#f59e0b', HIGH: '#ef4444' };
const LEVEL_LABELS = { LOW: '低活跃', MEDIUM: '中活跃', HIGH: '高活跃' };
const LEVEL_DIAL_PROGRESS = { LOW: 0.22, MEDIUM: 0.62, HIGH: 0.92 };
const STRATEGY_LABELS = {
  fixed: '固定策略',
  mab_ucb: '置信上界策略',
  mab_thompson: '汤普森采样策略',
};

const ARM_META = [
  { arm: 0, interval: 1, label: '逐段上链', note: '单段哈希即时锚定', scene: '变化明显时', accent: '#ff5a5a' },
  { arm: 1, interval: 2, label: '高频上链', note: '小批量哈希高频锚定', scene: '活动频繁时', accent: '#ff8c42' },
  { arm: 2, interval: 5, label: '均衡上链', note: '分组根哈希平衡锚定', scene: '常规运行时', accent: '#f7c948' },
  { arm: 3, interval: 10, label: '节能上链', note: '批量根哈希低频锚定', scene: '画面稳定时', accent: '#4ade80' },
];

const panelStyle = {
  background: 'var(--anchor-panel-bg)',
  border: '1px solid var(--anchor-panel-border)',
  boxShadow: 'var(--anchor-panel-shadow)',
  position: 'relative',
  overflow: 'hidden',
};

const microPanelStyle = {
  background: 'var(--anchor-micro-bg)',
  border: '1px solid var(--anchor-micro-border)',
  boxShadow: 'var(--anchor-micro-shadow)',
};

function clamp(value, min = 0, max = 1) {
  return Math.min(Math.max(Number(value) || 0, min), max);
}

function formatPercent(value) {
  if (!Number.isFinite(value)) return '0%';
  return `${Math.round(value)}%`;
}

function formatNumber(value) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return '0';
  return new Intl.NumberFormat('zh-CN').format(parsed);
}

function PanelTitle({ icon: Icon, label }) {
  return (
    <div style={{ display: 'inline-flex', alignItems: 'center', gap: '10px', color: 'var(--text-muted)', fontFamily: 'var(--font-heading)', fontSize: '0.86rem', fontWeight: 700, lineHeight: 1.2 }}>
      <Icon size={17} strokeWidth={2.2} />
      <span>{label}</span>
    </div>
  );
}

function getStrategyLabel(mode) {
  return STRATEGY_LABELS[mode] || mode || '未命名策略';
}

function getFallbackArm(interval) {
  return ARM_META.find((item) => item.interval === Number(interval)) || ARM_META[0];
}

function EISDial({ level, currentEIS }) {
  const color = LEVEL_COLORS[level] || LEVEL_COLORS.LOW;
  const displayProgress = LEVEL_DIAL_PROGRESS[level] ?? clamp(currentEIS);
  const percentage = displayProgress * 314;

  return (
    <section style={{ ...microPanelStyle, minHeight: '340px', padding: '18px', display: 'flex', flexDirection: 'column' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '12px' }}>
        <PanelTitle icon={Gauge} label="画面活跃度" />
      </div>

      <div style={{ position: 'relative', width: '224px', height: '224px', margin: 'auto' }}>
        <div
          className="eis-dial-glow"
          style={{
            position: 'absolute',
            inset: '24px',
            background: `radial-gradient(circle, ${color}2e, transparent 68%)`,
            borderRadius: '50%',
            filter: 'blur(16px)',
            opacity: 0.16,
          }}
        />
        <svg viewBox="0 0 120 120" style={{ width: '100%', height: '100%', overflow: 'visible' }}>
          <circle cx="60" cy="60" r="50" fill="none" stroke="var(--anchor-dial-track-wide)" strokeWidth="18" />
          <circle cx="60" cy="60" r="50" fill="none" stroke="var(--anchor-dial-track)" strokeWidth="8" />
          <circle
            className="eis-dial-ring"
            cx="60"
            cy="60"
            r="50"
            fill="none"
            stroke={color}
            strokeWidth="8"
            strokeLinecap="round"
            strokeDasharray={`${percentage} 314`}
            style={{ transform: 'rotate(-90deg)', transformOrigin: 'center', filter: `drop-shadow(0 0 10px ${color}66)`, transition: 'stroke-dasharray 240ms cubic-bezier(0.2, 0, 0, 1)' }}
          />
        </svg>
        <div style={{ position: 'absolute', inset: 0, display: 'grid', placeItems: 'center' }}>
          <div
            key={level}
            className="eis-dial-text"
            style={{ color, fontFamily: 'var(--font-heading)', fontSize: '1.42rem', fontWeight: 800, textAlign: 'center', textWrap: 'balance' }}
          >
            {LEVEL_LABELS[level] || level}
          </div>
        </div>
      </div>
    </section>
  );
}

function DecisionLink({ stats, accent, activeArm, currentInterval }) {
  const mode = getStrategyLabel(stats.mode);
  const currentLevel = stats.eis?.current_level || 'LOW';
  const currentEIS = Number(stats.eis?.current_eis || 0);
  const isMabEnabled = Boolean(stats.mab);
  const nodes = [
    {
      icon: Gauge,
      label: '画面活跃度指数输入',
      value: currentEIS.toFixed(2),
    },
    {
      icon: Brain,
      label: isMabEnabled ? '当前上链策略' : '固定上链策略',
      value: isMabEnabled ? `${activeArm.label}策略` : mode,
    },
    {
      icon: Route,
      label: 'GOP 锚定间隔',
      value: `${currentInterval} GOP`,
    },
  ];

  return (
    <section style={{ ...microPanelStyle, minHeight: '340px', padding: '18px', display: 'flex', flexDirection: 'column', overflow: 'hidden', minWidth: 0 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '12px', marginBottom: '18px' }}>
        <PanelTitle icon={ArrowRight} label="决策链路" />
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: '11px', alignItems: 'stretch', minWidth: 0 }}>
        {nodes.map((node, index) => {
          const Icon = node.icon;
          const isInputNode = index === 0;
          const isActiveNode = index === 1;
          const isIntervalNode = index === 2;
          const valueColor = isInputNode
            ? LEVEL_COLORS[currentLevel] || 'var(--text-pure)'
            : isActiveNode || isIntervalNode
              ? accent
              : 'var(--text-pure)';
          return (
            <div key={node.label} style={{ position: 'relative', minWidth: 0 }}>
              {index < nodes.length - 1 && (
                <div style={{ position: 'absolute', left: '50%', bottom: '-11px', width: '1px', height: '11px', background: `linear-gradient(180deg, ${accent}, var(--anchor-connector-fade))`, transform: 'translateX(-50%)', zIndex: 2 }} />
              )}
              <div
                className={isActiveNode ? 'anchor-decisionNode anchor-decisionNode--active' : 'anchor-decisionNode'}
                style={{
                  '--decision-accent': accent,
                  minHeight: isActiveNode ? '104px' : '78px',
                  padding: isActiveNode ? '16px 18px' : '12px 14px',
                  background: isActiveNode ? `linear-gradient(180deg, ${accent}1f, var(--anchor-node-active-tail))` : 'var(--anchor-node-bg)',
                  border: isActiveNode ? `1px solid ${accent}78` : '1px solid var(--anchor-node-border)',
                  boxShadow: isActiveNode ? `0 0 0 1px ${accent}18 inset, 0 18px 34px ${accent}10` : 'none',
                  display: 'grid',
                  gridTemplateColumns: '1fr',
                  alignItems: 'center',
                  gap: '12px',
                  width: isActiveNode ? '100%' : '86%',
                  margin: isActiveNode ? '0' : '0 auto',
                  minWidth: 0,
                }}
              >
                <div style={{ minWidth: 0, display: 'grid', justifyItems: 'center', textAlign: 'center' }}>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px', color: isActiveNode ? accent : 'var(--text-muted)', fontFamily: 'var(--font-heading)', fontSize: isActiveNode ? '0.72rem' : '0.66rem', marginBottom: isActiveNode ? '10px' : '8px', maxWidth: '100%' }}>
                    <Icon size={isActiveNode ? 16 : 14} />
                    <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', minWidth: 0 }}>{node.label}</span>
                  </div>
                  <div style={{ color: valueColor, fontFamily: 'var(--font-data)', fontSize: isActiveNode ? '1.46rem' : '1.06rem', fontWeight: 800, lineHeight: 1.1, fontVariantNumeric: 'tabular-nums', overflowWrap: 'anywhere', textAlign: 'center' }}>
                    {node.value}
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function OutputPanel({ stats, activeArm, currentInterval, savingPercent, anchorRate, accent }) {
  const isMabEnabled = Boolean(stats.mab);

  return (
    <section style={{ ...microPanelStyle, minHeight: '340px', padding: '18px', display: 'flex', flexDirection: 'column', justifyContent: 'space-between', overflow: 'hidden', minWidth: 0 }}>
      <div>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '12px' }}>
          <PanelTitle icon={RadioTower} label="上链输出" />
          <ShieldCheck size={16} color={accent} />
        </div>
        <div style={{ marginTop: '24px' }}>
          <div style={{ color: 'var(--text-dim)', fontSize: '0.68rem', marginBottom: '8px' }}>{isMabEnabled ? '自适应节能上链引擎' : '固定/EIS 策略模式'}</div>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: '10px', flexWrap: 'wrap', minWidth: 0 }}>
            <strong style={{ color: accent, fontFamily: 'var(--font-data)', fontSize: 'clamp(2.25rem, 4vw, 2.75rem)', lineHeight: 0.9, fontVariantNumeric: 'tabular-nums' }}>{currentInterval}</strong>
            <span style={{ color: accent, fontFamily: 'var(--font-data)', fontSize: '1rem', letterSpacing: '0.08em' }}>GOP</span>
          </div>
          <p style={{ marginTop: '10px', color: 'var(--text-muted)', fontSize: '0.78rem', lineHeight: 1.6 }}>
            {isMabEnabled
              ? `${activeArm.label}策略正在生效，${activeArm.note}。`
              : 'MAB 未启用时，锚定间隔由固定/EIS 策略注入。'}
          </p>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: '10px' }}>
        <CompactMetric label="预计节省资源" value={formatPercent(savingPercent)} tone="var(--nv-green)" />
        <CompactMetric label="实际锚定比例" value={formatPercent(anchorRate)} tone={accent} />
        <CompactMetric label="策略决策总数" value={formatNumber(stats.mab?.total_decisions || 0)} tone="var(--text-pure)" />
        <CompactMetric label="链上锚定次数" value={formatNumber(stats.mab?.anchor_count || 0)} tone="var(--text-pure)" />
      </div>
    </section>
  );
}

function CompactMetric({ label, value, tone }) {
  return (
    <div style={{ padding: '12px', minHeight: '76px', background: 'var(--anchor-compact-bg)', border: '1px solid var(--anchor-compact-border)', minWidth: 0, overflow: 'hidden', boxShadow: 'var(--anchor-compact-shadow)' }}>
      <div style={{ color: 'var(--text-dim)', fontSize: '0.62rem', marginBottom: '10px' }}>{label}</div>
      <div style={{ color: tone, fontFamily: 'var(--font-data)', fontWeight: 800, fontSize: 'clamp(1.18rem, 1.55vw, 1.42rem)', fontVariantNumeric: 'tabular-nums', overflowWrap: 'anywhere', lineHeight: 1 }}>{value}</div>
    </div>
  );
}

function StrategyRail({ currentArm, currentInterval }) {
  return (
    <section className="anchor-strategyRail" aria-label="自适应上链频率">
      <div className="anchor-strategyRail__header">
        <span className="anchor-strategyRail__title">
          <BarChart3 size={14} /> 自适应上链频率
        </span>
        <span className="anchor-strategyRail__readout">{currentInterval} GOP 当前间隔</span>
      </div>
      <div className="anchor-strategyGrid">
        {ARM_META.map((arm) => {
          const isActive = currentArm === arm.arm || (!Number.isFinite(currentArm) && Number(currentInterval) === arm.interval);
          const savings = arm.interval > 1 ? Math.round((1 - 1 / arm.interval) * 100) : 0;

          return (
            <article
              key={arm.arm}
              className={`anchor-strategyCard${isActive ? ' is-active' : ''}`}
              style={{ '--arm-accent': arm.accent, '--arm-progress': `${Math.round(100 / arm.interval)}%` }}
              aria-current={isActive ? 'true' : undefined}
            >
              <span className="anchor-strategyCard__scan" />
              <div className="anchor-strategyCard__top">
                <div className="anchor-strategyCard__metric">
                  <strong>{arm.interval}</strong>
                  <span>GOP</span>
                </div>
                <span className="anchor-strategyCard__beacon" />
              </div>
              <div className="anchor-strategyCard__label">{arm.label}</div>
              <div className="anchor-strategyCard__scene">{arm.scene}</div>
              <div className="anchor-strategyCard__note">{arm.note}</div>
              <div className="anchor-strategyCard__meter" aria-hidden="true">
                <span />
              </div>
              <div className="anchor-strategyCard__footer">
                <span>{savings > 0 ? `约节省 ${savings}% 资源` : '性能模式'}</span>
                <strong>{isActive ? '当前生效' : '候选策略'}</strong>
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}

function AnchorDecisionEngine({ stats }) {
  const currentLevel = stats.eis?.current_level || 'LOW';
  const currentEIS = Number(stats.eis?.current_eis || 0);
  const currentInterval = Number(stats.mab?.current_interval || stats.anchor?.segment_gops || 1);
  const activeArm = stats.mab ? getFallbackArm(stats.mab.current_interval) : getFallbackArm(currentInterval);
  const accent = stats.mab
    ? ARM_META.find((item) => item.arm === stats.mab.current_arm)?.accent || activeArm.accent
    : LEVEL_COLORS[currentLevel] || activeArm.accent;
  const savingPercent = currentInterval > 1 ? Math.max(0, 1 - 1 / currentInterval) * 100 : 0;
  const anchorRate = stats.mab?.total_decisions > 0
    ? (stats.mab.anchor_count / stats.mab.total_decisions) * 100
    : 0;
  return (
    <div className="anchor-decisionEngine" style={{ ...panelStyle, padding: '20px' }}>
      <div style={{ position: 'absolute', inset: 0, pointerEvents: 'none', background: `radial-gradient(circle at 20% 8%, ${LEVEL_COLORS[currentLevel] || accent}16, transparent 34%), radial-gradient(circle at 82% 0%, ${accent}12, transparent 36%)` }} />
      <div style={{ position: 'relative' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '18px', marginBottom: '16px', flexWrap: 'wrap' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', color: 'var(--nv-green)', fontFamily: 'var(--font-heading)', fontSize: '0.84rem', fontWeight: 700, marginBottom: '8px', lineHeight: 1.2 }}>
              <Zap size={18} strokeWidth={2.2} /> 智能锚定决策引擎
            </div>
            <h2 style={{ margin: 0, fontSize: '1.12rem', letterSpacing: '0.04em' }}>画面自适应锚定引擎</h2>
          </div>
          <div style={{ color: 'var(--text-muted)', fontSize: '0.74rem', lineHeight: 1.55, maxWidth: '420px' }}>
            活跃度先判断画面变化强度，再选择合适的上链策略，最终动态调整 GOP 锚定间隔。
          </div>
        </div>

        <div className="anchor-engineGrid">
          <EISDial level={currentLevel} currentEIS={currentEIS} />
          <DecisionLink
            stats={stats}
            accent={accent}
            activeArm={activeArm}
            currentInterval={currentInterval}
            savingPercent={savingPercent}
            anchorRate={anchorRate}
          />
          <OutputPanel
            stats={stats}
            activeArm={activeArm}
            currentInterval={currentInterval}
            savingPercent={savingPercent}
            anchorRate={anchorRate}
            accent={accent}
          />
        </div>

        <StrategyRail currentArm={Number(stats.mab?.current_arm)} currentInterval={currentInterval} />
      </div>
    </div>
  );
}

export default function AnchorPage() {
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchStats = async () => {
    try {
      setLoading(true);
      const data = await getAnchorStats();
      setStats(data);
      setError(null);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchStats();
    const interval = setInterval(fetchStats, 5000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div style={{ padding: '22px 24px 18px', maxWidth: '1360px', minHeight: 'calc(100vh - 24px)', display: 'flex', flexDirection: 'column' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '18px', gap: '18px', flexWrap: 'wrap' }}>
        <div>
          <h1 style={{ fontFamily: 'var(--font-heading)', fontSize: '1.4rem', fontWeight: 700, margin: 0 }}>
            <Zap size={20} style={{ verticalAlign: 'middle', marginRight: '8px', color: 'var(--nv-green)' }} />
            智能锚定控制台
          </h1>
        </div>
        <button
          onClick={fetchStats}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            minHeight: '40px',
            padding: '8px 16px',
            border: '1px solid var(--border-subtle)',
            background: 'var(--anchor-refresh-bg)',
            color: 'var(--text-muted)',
            cursor: 'pointer',
            fontFamily: 'var(--font-heading)',
            fontSize: '0.8rem',
            transitionProperty: 'border-color, background-color, color, transform',
            transitionDuration: '200ms',
            transitionTimingFunction: 'cubic-bezier(0.2, 0, 0, 1)',
          }}
        >
          <RefreshCw size={14} className={loading ? 'spin' : ''} /> 刷新
        </button>
      </div>

      {error && (
        <div style={{ padding: '16px', background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)', color: '#ef4444', fontSize: '0.85rem', marginBottom: '20px' }}>
          {error}
        </div>
      )}

      {stats && <AnchorDecisionEngine stats={stats} />}

      {!stats && !error && (
        <div style={{ ...panelStyle, padding: '26px', color: 'var(--text-muted)', fontFamily: 'var(--font-heading)', fontSize: '0.8rem' }}>
          <Timer size={15} className={loading ? 'spin' : ''} style={{ verticalAlign: 'middle', marginRight: '8px' }} />
          正在同步智能锚定状态
        </div>
      )}
    </div>
  );
}
