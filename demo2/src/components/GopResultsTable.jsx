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
      className="scrollbar-hide" 
      style={{ 
        height: '100%', 
        maxHeight: '440px', 
        overflowY: 'auto',
        background: 'rgba(0, 0, 0, 0.2)',
        borderRadius: '8px',
        border: '1px solid var(--border-subtle)',
        boxShadow: 'inset 0 2px 10px rgba(0,0,0,0.2)',
      }}
    >
      <div style={{ 
        display: 'grid', 
        gridTemplateColumns: '60px 80px 1fr 120px', 
        gap: '16px', 
        alignItems: 'center', 
        position: 'sticky', 
        top: 0, 
        background: 'rgba(20, 20, 20, 0.85)', 
        backdropFilter: 'blur(8px)',
        WebkitBackdropFilter: 'blur(8px)',
        zIndex: 10, 
        padding: '12px 16px', 
        borderBottom: '1px solid var(--border-subtle)', 
        color: 'var(--text-dim)', 
        fontSize: '0.75rem', 
        fontWeight: 600, 
        letterSpacing: '0.04em' 
      }}>
        <span># GOP</span>
        <span style={{ textAlign: 'center' }}>状态</span>
        <span>风险程度</span>
        <span>详情 / 标签</span>
      </div>
      
      <div style={{ padding: '8px 16px', display: 'flex', flexDirection: 'column', gap: '4px' }}>
        {gopResults.map((gop) => {
          const cfg = STATUS_COLORS[gop.status] || STATUS_COLORS.TAMPERED;
          const pct = Math.min(Math.max((gop.risk || 0) * 100, 0), 100);
          
          return (
            <div 
              key={gop.gop_index} 
              style={{ 
                display: 'grid', 
                gridTemplateColumns: '60px 80px 1fr 120px', 
                gap: '16px', 
                alignItems: 'center', 
                padding: '8px 0',
                borderBottom: '1px dashed rgba(255,255,255,0.05)',
                fontSize: '0.85rem',
                transition: 'background-color 0.2s ease',
              }}
              onMouseEnter={(e) => e.currentTarget.style.backgroundColor = 'rgba(255,255,255,0.02)'}
              onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'transparent'}
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
              
              <div style={{ 
                height: '6px', 
                background: 'rgba(255, 255, 255, 0.08)', 
                borderRadius: '3px',
                position: 'relative',
                overflow: 'hidden',
              }}>
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
