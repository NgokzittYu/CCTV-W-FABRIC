import { useState } from 'react';
import { Shield, AlertTriangle, Search, Crosshair, Zap } from 'lucide-react';
import GlassCard from '../components/GlassCard';
import StatusBadge from '../components/StatusBadge';
import { verificationScenarios, tamperTypes } from '../data/mockData';

export default function VerificationPage() {
  const [selectedScenario, setSelectedScenario] = useState(0);
  const [selectedTamper, setSelectedTamper] = useState(null);
  const s = verificationScenarios[selectedScenario];

  return (
    <div className="page-container">
      <div className="section-header">
        <h2 className="section-title"><Shield size={24} className="text-green" /> 审计验证引擎</h2>
        <p className="section-subtitle">三态验证 + 篡改定位 + 攻击场景模拟</p>
      </div>

      {/* Tri-State Verification */}
      <section className="section">
        <h3 style={{marginBottom:16,display:'flex',alignItems:'center',gap:10}}>
          <Zap size={18} className="text-purple" /> 三态验证引擎
        </h3>

        <div style={{display:'flex',gap:8,marginBottom:24}}>
          {verificationScenarios.map((sc,i)=>(
            <button key={sc.state} className={`btn ${selectedScenario===i?'':'btn-ghost'}`}
              style={selectedScenario===i?{background:`${sc.color}20`,color:sc.color,border:`1px solid ${sc.color}50`}:{}}
              onClick={()=>setSelectedScenario(i)}>
              {sc.name}
            </button>
          ))}
        </div>

        <div className="grid-2">
          <GlassCard glowColor={s.color} hover={false}>
            <div style={{textAlign:'center',padding:'20px 0'}}>
              <svg viewBox="0 0 200 120" width="200" height="120" style={{margin:'0 auto',display:'block'}}>
                <path d="M 20 100 A 80 80 0 0 1 180 100" fill="none" stroke="var(--border-color)" strokeWidth="8" strokeLinecap="round"/>
                <path d="M 20 100 A 80 80 0 0 1 180 100" fill="none" stroke={s.color} strokeWidth="8" strokeLinecap="round"
                  strokeDasharray={`${s.risk*251} 251`}
                  style={{transition:'stroke-dasharray 600ms cubic-bezier(0.23,1,0.32,1),stroke 300ms ease'}}/>
                {/* Threshold marker at 0.35 */}
                <line x1={20+0.35*160} y1="15" x2={20+0.35*160} y2="25" stroke="var(--accent-amber)" strokeWidth="2" strokeDasharray="3 2"/>
                <text x={20+0.35*160} y="12" textAnchor="middle" fill="var(--accent-amber)" style={{fontSize:'7px'}}>0.35</text>
                <text x="100" y="80" textAnchor="middle" fill={s.color} style={{fontSize:'28px',fontFamily:'var(--font-display)',fontWeight:700}}>
                  {s.risk.toFixed(2)}
                </text>
                <text x="100" y="100" textAnchor="middle" fill="var(--text-muted)" style={{fontSize:'10px'}}>Risk Score</text>
              </svg>
              <div style={{marginTop:16}}><StatusBadge state={s.state}/></div>
            </div>
          </GlassCard>

          <GlassCard hover={false}>
            <h4 style={{marginBottom:16}}>{s.name} ({s.nameEn})</h4>
            <div style={{display:'flex',flexDirection:'column',gap:12,fontSize:'0.85rem'}}>
              <div style={{display:'flex',justifyContent:'space-between'}}>
                <span className="text-muted">SHA-256 匹配</span>
                <span style={{color:s.shaMatch?'var(--accent-green)':'var(--accent-red)',fontWeight:600}}>
                  {s.shaMatch?'✓ 匹配':'✗ 不匹配'}
                </span>
              </div>
              <div style={{display:'flex',justifyContent:'space-between'}}>
                <span className="text-muted">Hamming 距离</span>
                <span>{s.hammingDist}/256 ({(s.hammingDist/256).toFixed(3)})</span>
              </div>
              <div style={{display:'flex',justifyContent:'space-between'}}>
                <span className="text-muted">阈值</span>
                <span className="text-amber">0.35 (P99 包络)</span>
              </div>
              <div style={{paddingTop:12,borderTop:'1px solid var(--border-color)'}}>
                <p>{s.desc}</p>
              </div>
            </div>
          </GlassCard>
        </div>
      </section>

      {/* Tamper Localization */}
      <section className="section">
        <h3 style={{marginBottom:16,display:'flex',alignItems:'center',gap:10}}>
          <Crosshair size={18} className="text-red" /> 篡改定位演示
        </h3>

        <GlassCard hover={false}>
          <p style={{fontSize:'0.85rem',marginBottom:16}}>
            通过 Merkle 路径二分查找，可精确定位被篡改的 GOP 位置（精度 1-2 秒）
          </p>
          <div style={{display:'flex',gap:8,flexWrap:'wrap'}}>
            {Array.from({length:12},(_,i)=>{
              const tampered = i===3||i===7;
              return (
                <div key={i} style={{
                  padding:'12px 16px',borderRadius:8,
                  background:tampered?'var(--accent-red-dim)':'var(--bg-secondary)',
                  border:`1px solid ${tampered?'rgba(239,68,68,0.3)':'var(--border-color)'}`,
                  textAlign:'center',minWidth:60,
                  transition:'all 200ms ease',cursor:'pointer',
                }}>
                  <div style={{fontSize:'0.75rem',fontWeight:600,color:tampered?'var(--accent-red)':'var(--text-primary)'}}>
                    GOP {i}
                  </div>
                  <div style={{fontSize:'0.6rem',color:'var(--text-muted)',marginTop:2}}>
                    {(i*1.2).toFixed(1)}s
                  </div>
                  {tampered&&<div style={{fontSize:'0.55rem',color:'var(--accent-red)',marginTop:4,fontWeight:600}}>⚠ 篡改</div>}
                </div>
              );
            })}
          </div>
          <div style={{marginTop:16,padding:'10px 14px',borderRadius:8,background:'var(--accent-red-dim)',fontSize:'0.8rem',color:'var(--accent-red)'}}>
            <AlertTriangle size={14} style={{display:'inline',marginRight:6,verticalAlign:'middle'}}/>
            检测到 2 个 GOP 被篡改: GOP 3 (3.6s), GOP 7 (8.4s) — 通过 SegmentRoot → ChunkRoot → Leaf 二分定位
          </div>
        </GlassCard>
      </section>

      {/* Attack Scenarios */}
      <section className="section">
        <h3 style={{marginBottom:16,display:'flex',alignItems:'center',gap:10}}>
          <Search size={18} className="text-amber" /> 攻击场景模拟
        </h3>
        <div className="grid-2">
          {tamperTypes.map((t,i)=>(
            <GlassCard key={t.id}
              glowColor={t.severity==='high'?'#EF4444':t.severity==='medium'?'#F59E0B':'#22C55E'}
              onClick={()=>setSelectedTamper(selectedTamper===i?null:i)}
              className={`animate-fade-in-up stagger-${i+1}`}>
              <div style={{display:'flex',justifyContent:'space-between',alignItems:'center'}}>
                <h4>{t.name}</h4>
                <span className={`badge ${t.severity==='high'?'badge-tampered':t.severity==='medium'?'badge-re-encoded':'badge-intact'}`}>
                  {t.severity==='high'?'高危':t.severity==='medium'?'中危':'低危'}
                </span>
              </div>
              <p style={{fontSize:'0.8rem',marginTop:8}}>{t.desc}</p>
              <div style={{marginTop:12,padding:'8px 12px',borderRadius:6,background:'var(--bg-secondary)',display:'flex',justifyContent:'space-between',fontSize:'0.8rem'}}>
                <span className="text-muted">VIF 距离</span>
                <span style={{fontWeight:600,fontFamily:'var(--font-display)',color:t.vifDist>=0.35?'var(--accent-red)':'var(--accent-green)'}}>
                  {t.vifDist.toFixed(2)}
                </span>
              </div>
              <div style={{marginTop:6,height:4,borderRadius:2,background:'var(--bg-secondary)'}}>
                <div style={{width:`${t.vifDist*100}%`,height:'100%',borderRadius:2,background:t.vifDist>=0.35?'var(--accent-red)':'var(--accent-green)',transition:'width 600ms var(--ease-out)'}}/>
              </div>
            </GlassCard>
          ))}
        </div>
      </section>
    </div>
  );
}
