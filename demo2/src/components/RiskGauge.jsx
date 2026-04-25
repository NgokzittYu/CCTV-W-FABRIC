import { useMemo } from 'react';

const STATUS_CONFIG = {
  INTACT: {
    label: '原档完好',
    color: 'var(--nv-green)',
    bgColor: 'var(--nv-green-dim)',
    desc: 'SHA-256 MATCH // 无偏差',
  },
  RE_ENCODED: {
    label: '合法转码',
    color: 'var(--status-warn)',
    bgColor: 'var(--status-warn-dim)',
    desc: 'VIF_TOLERANCE // 容忍偏差',
  },
  TAMPERED: {
    label: '篡改嫌疑',
    color: 'var(--status-err)',
    bgColor: 'var(--status-err-dim)',
    desc: 'FATAL // VIF_DEVIATION_ALERT 特征异动',
  },
};

/**
 * Animated SVG gauge visualizing risk level with tri-state coloring.
 */
export default function RiskGauge({ status = 'INTACT', risk = 0, size = 160 }) {
  const config = STATUS_CONFIG[status] || STATUS_CONFIG.INTACT;
  const percentage = Math.min(Math.max(risk * 100, 0), 100);

  // SVG arc calculation
  const cx = size / 2;
  const cy = size * 0.55; 
  const radius = (size - 24) / 2;

  const riskLabel = useMemo(() => {
    if (percentage <= 5) return '极低';
    if (percentage <= 20) return '低';
    if (percentage <= 50) return '中';
    if (percentage <= 80) return '高';
    return '极高';
  }, [percentage]);

  return (
    <div
      className="risk-gauge"
      style={{
        width: size,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: '12px',
      }}
    >
      <div
        style={{
          position: 'relative',
          width: size,
          height: size * 0.65,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <svg
          viewBox={`0 0 ${size} ${size * 0.65}`}
          width={size}
          height={size * 0.65}
          style={{ position: 'absolute', top: 0, left: 0 }}
        >
          {/* Background Arc */}
          <path
            d={describeArc(cx, cy, radius, -90, 90)}
            fill="none"
            stroke="rgba(255, 255, 255, 0.06)"
            strokeWidth={14}
            strokeLinecap="round"
          />
          {/* Value Arc */}
          <path
            d={describeArc(cx, cy, radius, -90, -90 + (percentage / 100) * 180)}
            fill="none"
            stroke={config.color}
            strokeWidth={14}
            strokeLinecap="round"
            style={{
              filter: `drop-shadow(0 0 12px ${config.color}60)`,
              transitionProperty: 'd, stroke, filter',
              transitionDuration: '1s',
              transitionTimingFunction: 'cubic-bezier(0.23, 1, 0.32, 1)',
            }}
          />
        </svg>

        <div
          style={{
            position: 'absolute',
            inset: 0,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'flex-end',
            paddingBottom: '8px',
            pointerEvents: 'none',
          }}
        >
          <div
            style={{
              display: 'flex',
              alignItems: 'baseline',
              gap: '6px',
              lineHeight: 1,
            }}
          >
            <span
              style={{
                color: config.color,
                fontFamily: 'var(--font-heading)',
                fontSize: `${Math.max(size * 0.18, 24)}px`,
                fontWeight: 700,
                letterSpacing: '-0.02em',
                fontVariantNumeric: 'tabular-nums',
                textShadow: `0 2px 10px ${config.color}30`
              }}
            >
              {percentage.toFixed(1)}%
            </span>
            <span
              style={{
                color: 'var(--text-muted)',
                fontFamily: 'var(--font-heading)',
                fontSize: `${Math.max(size * 0.05, 12)}px`,
                letterSpacing: '0.06em',
              }}
            >
              {riskLabel}风险
            </span>
          </div>
          <div
            style={{
              marginTop: '12px',
              padding: '6px 14px',
              background: config.bgColor,
              color: config.color,
              borderRadius: '6px',
              border: `1px solid ${config.color}40`,
              boxShadow: `0 2px 10px ${config.color}15, inset 0 1px 0 ${config.color}20`,
              fontFamily: 'var(--font-heading)',
              fontSize: `${Math.max(size * 0.06, 14)}px`,
              fontWeight: 600,
              letterSpacing: '0.04em',
            }}
          >
            {config.label}
          </div>
        </div>
      </div>

      <div
        style={{
          color: 'var(--text-dim)',
          fontFamily: 'var(--font-data)',
          fontSize: '0.8rem',
          letterSpacing: '0.04em',
          textAlign: 'center',
          textWrap: 'pretty',
        }}
      >
        {config.desc}
      </div>
    </div>
  );
}

/**
 * Helper to describe an SVG arc path.
 */
function describeArc(cx, cy, radius, startAngle, endAngle) {
  // Add a tiny epsilon if angles are identical to avoid SVG rendering issues with zero-length arcs
  if (startAngle === endAngle) {
    endAngle += 0.001;
  }
  const start = polarToCartesian(cx, cy, radius, startAngle);
  const end = polarToCartesian(cx, cy, radius, endAngle);
  const largeArcFlag = Math.abs(endAngle - startAngle) <= 180 ? '0' : '1';
  // Sweep flag 1 means clockwise
  return `M ${start.x} ${start.y} A ${radius} ${radius} 0 ${largeArcFlag} 1 ${end.x} ${end.y}`;
}

function polarToCartesian(cx, cy, radius, angleDeg) {
  const angleRad = ((angleDeg - 90) * Math.PI) / 180.0;
  return {
    x: cx + radius * Math.cos(angleRad),
    y: cy + radius * Math.sin(angleRad),
  };
}
