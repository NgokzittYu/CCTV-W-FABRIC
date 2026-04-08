import { useMemo } from 'react';

const STATUS_CONFIG = {
  INTACT: {
    label: '原档完好',
    color: '#22C55E',
    bgColor: 'rgba(34, 197, 94, 0.12)',
    desc: 'SHA-256 完全匹配，视频未被修改',
  },
  RE_ENCODED: {
    label: '合法转码',
    color: '#F59E0B',
    bgColor: 'rgba(245, 158, 11, 0.12)',
    desc: '视频经过重编码，VIF 指纹在宽容带内',
  },
  TAMPERED: {
    label: '篡改嫌疑',
    color: '#EF4444',
    bgColor: 'rgba(239, 68, 68, 0.12)',
    desc: 'VIF 偏离超过安全阈值，存在篡改风险',
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
  const cy = size / 2;
  const radius = (size - 20) / 2;
  const circumference = Math.PI * radius; // half circle
  const dashOffset = circumference - (percentage / 100) * circumference;

  const riskLabel = useMemo(() => {
    if (percentage <= 5) return '极低';
    if (percentage <= 20) return '低';
    if (percentage <= 50) return '中';
    if (percentage <= 80) return '高';
    return '极高';
  }, [percentage]);

  return (
    <div className="risk-gauge" style={{ width: size, height: size * 0.7 }}>
      <svg
        viewBox={`0 0 ${size} ${size * 0.65}`}
        width={size}
        height={size * 0.65}
      >
        {/* Background arc */}
        <path
          d={describeArc(cx, size * 0.55, radius, 180, 360)}
          fill="none"
          stroke="rgba(148, 163, 184, 0.1)"
          strokeWidth={10}
          strokeLinecap="round"
        />
        {/* Filled arc */}
        <path
          d={describeArc(cx, size * 0.55, radius, 180, 180 + (percentage / 100) * 180)}
          fill="none"
          stroke={config.color}
          strokeWidth={10}
          strokeLinecap="round"
          style={{
            filter: `drop-shadow(0 0 6px ${config.color}50)`,
            transition: 'all 0.8s cubic-bezier(0.23, 1, 0.32, 1)',
          }}
        />
      </svg>

      {/* Center text */}
      <div className="risk-gauge-center">
        <span className="risk-gauge-value" style={{ color: config.color }}>
          {percentage.toFixed(1)}%
        </span>
        <span className="risk-gauge-label">{riskLabel}风险</span>
      </div>

      {/* Status badge */}
      <div
        className="risk-gauge-status"
        style={{
          background: config.bgColor,
          color: config.color,
          border: `1px solid ${config.color}30`,
        }}
      >
        {config.label}
      </div>
    </div>
  );
}

/**
 * Helper to describe an SVG arc path.
 */
function describeArc(cx, cy, radius, startAngle, endAngle) {
  const start = polarToCartesian(cx, cy, radius, endAngle);
  const end = polarToCartesian(cx, cy, radius, startAngle);
  const largeArcFlag = endAngle - startAngle <= 180 ? '0' : '1';
  return `M ${start.x} ${start.y} A ${radius} ${radius} 0 ${largeArcFlag} 0 ${end.x} ${end.y}`;
}

function polarToCartesian(cx, cy, radius, angleDeg) {
  const angleRad = ((angleDeg - 90) * Math.PI) / 180.0;
  return {
    x: cx + radius * Math.cos(angleRad),
    y: cy + radius * Math.sin(angleRad),
  };
}
