import { memo } from 'react';

const STATUS_COLORS = {
  INTACT:     { color: 'var(--nv-green)',    bg: 'var(--nv-green-dim)',    label: '完好' },
  RE_ENCODED: { color: 'var(--status-warn)', bg: 'var(--status-warn-dim)', label: '转码' },
  TAMPERED:   { color: 'var(--status-err)',  bg: 'var(--status-err-dim)',  label: '篡改嫌疑' },
};

export default memo(function GopResultsTable({ gopResults = [] }) {
  if (!gopResults.length) return null;

  return (
    <div 
      className="gop-results-table scrollbar-hide"
    >
      <div className="gop-results-table__head">
        <span># GOP</span>
        <span style={{ textAlign: 'center' }}>状态</span>
        <span>风险程度</span>
        <span>详情 / 标签</span>
      </div>
      
      <div className="gop-results-table__body">
        {gopResults.map((gop) => {
          const cfg = STATUS_COLORS[gop.status] || STATUS_COLORS.TAMPERED;
          const pct = Math.min(Math.max((gop.risk || 0) * 100, 0), 100);
          
          return (
            <div 
              key={gop.gop_index} 
              className="gop-results-table__row"
            >
              <span style={{ color: 'var(--text-muted)', fontVariantNumeric: 'tabular-nums', fontWeight: 500 }}>
                {String(gop.gop_index).padStart(3, '0')}
              </span>
              
              <div style={{ display: 'flex', justifyContent: 'center' }}>
                <span style={{ 
                  padding: '4px 10px', 
                  fontSize: '0.75rem', 
                  background: cfg.bg, 
                  color: cfg.color, 
                  border: `1px solid ${cfg.color}30`, 
                  borderRadius: '4px',
                  fontWeight: 600,
                  letterSpacing: '0.04em',
                }}>
                  {cfg.label}
                </span>
              </div>
              
              <div className="gop-results-table__meter">
                <div style={{ 
                  position: 'absolute', 
                  left: 0, top: 0, bottom: 0, 
                  width: `${pct}%`, 
                  background: cfg.color, 
                  transition: 'width 0.8s cubic-bezier(0.23, 1, 0.32, 1)',
                  boxShadow: `0 0 10px ${cfg.color}`
                }} />
              </div>
              
              <span style={{ 
                color: 'var(--text-dim)', 
                fontSize: '0.75rem', 
                fontFamily: 'var(--font-data)',
                overflow: 'hidden', 
                textOverflow: 'ellipsis', 
                whiteSpace: 'nowrap' 
              }}>
                {gop.detail || gop.status}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
});
