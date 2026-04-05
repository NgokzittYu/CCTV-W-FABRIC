import { BarChart3, TrendingUp, Clock, Zap } from 'lucide-react';
import GlassCard from '../components/GlassCard';
import AnimatedCounter from '../components/AnimatedCounter';
import { benchmarkMAB, benchmarkVIF, benchmarkCost, performanceMetrics } from '../data/mockData';

export default function BenchmarkPage() {
  const maxTx = Math.max(...benchmarkCost.txPerHour);

  return (
    <div className="page-container">
      <div className="section-header">
        <h2 className="section-title"><BarChart3 size={24} className="text-cyan" /> 对比实验与基准测试</h2>
        <p className="section-subtitle">MAB 策略对比、VIF 版本对比、成本分析与性能指标</p>
      </div>

      {/* MAB Strategy Comparison */}
      <section className="section">
        <h3 style={{marginBottom:16,display:'flex',alignItems:'center',gap:10}}>
          <TrendingUp size={18} className="text-purple" /> MAB 策略对比
        </h3>
        <GlassCard hover={false}>
          <div style={{display:'flex',gap:20,marginBottom:16,fontSize:'0.75rem'}}>
            <span><span style={{display:'inline-block',width:12,height:3,background:'var(--accent-purple)',borderRadius:2,marginRight:6}}/>UCB1</span>
            <span><span style={{display:'inline-block',width:12,height:3,background:'var(--accent-blue)',borderRadius:2,marginRight:6}}/>Thompson</span>
            <span><span style={{display:'inline-block',width:12,height:3,background:'var(--text-muted)',borderRadius:2,marginRight:6}}/>Fixed</span>
          </div>
          <svg viewBox="0 0 800 250" width="100%" height="250" style={{background:'var(--bg-secondary)',borderRadius:8,padding:8}}>
            {[0,0.25,0.5,0.75,1].map(y=>(
              <g key={y}>
                <line x1="40" y1={220-y*200} x2="780" y2={220-y*200} stroke="var(--border-color)" strokeWidth="0.5"/>
                <text x="35" y={224-y*200} textAnchor="end" fill="var(--text-muted)" style={{fontSize:'8px'}}>{y.toFixed(2)}</text>
              </g>
            ))}
            {/* UCB1 */}
            <polyline fill="none" stroke="var(--accent-purple)" strokeWidth="2"
              points={benchmarkMAB.ucb1.map((v,i)=>`${40+i*38.9},${220-v*200}`).join(' ')}/>
            {/* Thompson */}
            <polyline fill="none" stroke="var(--accent-blue)" strokeWidth="2" strokeDasharray="6 3"
              points={benchmarkMAB.thompson.map((v,i)=>`${40+i*38.9},${220-v*200}`).join(' ')}/>
            {/* Fixed */}
            <polyline fill="none" stroke="var(--text-muted)" strokeWidth="1.5" strokeDasharray="4 4"
              points={benchmarkMAB.fixed.map((v,i)=>`${40+i*38.9},${220-v*200}`).join(' ')}/>
            {/* X labels */}
            {benchmarkMAB.labels.filter((_,i)=>i%4===0).map((l,i)=>(
              <text key={l} x={40+i*4*38.9} y="240" textAnchor="middle" fill="var(--text-muted)" style={{fontSize:'7px'}}>Step {l}</text>
            ))}
          </svg>
          <p style={{fontSize:'0.75rem',color:'var(--text-muted)',marginTop:8,textAlign:'center'}}>
            累计 Avg Reward 对比：UCB1 和 Thompson 均显著优于固定策略
          </p>
        </GlassCard>
      </section>

      {/* VIF Version Comparison */}
      <section className="section">
        <h3 style={{marginBottom:16,display:'flex',alignItems:'center',gap:10}}>
          <Zap size={18} className="text-green" /> VIF 版本对比
        </h3>
        <GlassCard hover={false}>
          <div style={{overflowX:'auto'}}>
            <table style={{width:'100%',borderCollapse:'collapse',fontSize:'0.8rem'}}>
              <thead>
                <tr>
                  <th style={{padding:'10px 14px',textAlign:'left',borderBottom:'1px solid var(--border-color)',fontSize:'0.7rem',textTransform:'uppercase',letterSpacing:'0.05em',color:'var(--text-muted)'}}>指标</th>
                  {benchmarkVIF.versions.map((v,i)=>(
                    <th key={v} style={{padding:'10px 14px',textAlign:'center',borderBottom:'1px solid var(--border-color)',fontSize:'0.7rem',color:i===2?'var(--accent-green)':'var(--text-muted)'}}>{v}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td style={{padding:'10px 14px',borderBottom:'1px solid var(--border-color)',fontWeight:600}}>误报率 (%)</td>
                  {benchmarkVIF.falsePositive.map((v,i)=>(<td key={i} style={{padding:'10px 14px',textAlign:'center',borderBottom:'1px solid var(--border-color)',color:v===0?'var(--accent-green)':'var(--accent-red)'}}>{v}</td>))}
                </tr>
                <tr>
                  <td style={{padding:'10px 14px',borderBottom:'1px solid var(--border-color)',fontWeight:600}}>漏报率 (%)</td>
                  {benchmarkVIF.falseNegative.map((v,i)=>(<td key={i} style={{padding:'10px 14px',textAlign:'center',borderBottom:'1px solid var(--border-color)',color:v<5?'var(--accent-green)':v<10?'var(--accent-amber)':'var(--accent-red)'}}>{v}</td>))}
                </tr>
                <tr>
                  <td style={{padding:'10px 14px',borderBottom:'1px solid var(--border-color)',fontWeight:600}}>计算延迟 (ms)</td>
                  {benchmarkVIF.computeTimeMs.map((v,i)=>(<td key={i} style={{padding:'10px 14px',textAlign:'center',borderBottom:'1px solid var(--border-color)',color:'var(--text-secondary)'}}>{v}</td>))}
                </tr>
                <tr>
                  <td style={{padding:'10px 14px',fontWeight:600}}>容忍转码</td>
                  {benchmarkVIF.tolerateReencode.map((v,i)=>(<td key={i} style={{padding:'10px 14px',textAlign:'center',color:v?'var(--accent-green)':'var(--accent-red)',fontWeight:600}}>{v?'✓':'✗'}</td>))}
                </tr>
              </tbody>
            </table>
          </div>
        </GlassCard>
      </section>

      {/* Cost Analysis */}
      <section className="section">
        <h3 style={{marginBottom:16,display:'flex',alignItems:'center',gap:10}}>
          <BarChart3 size={18} className="text-amber" /> 成本分析
        </h3>
        <GlassCard hover={false}>
          <div style={{display:'flex',gap:12,alignItems:'flex-end',height:180,marginBottom:16}}>
            {benchmarkCost.frequency.map((f,i)=>{
              const isMAB = i===4;
              const h = (benchmarkCost.txPerHour[i]/maxTx)*160;
              return (
                <div key={f} style={{flex:1,display:'flex',flexDirection:'column',alignItems:'center'}}>
                  <span style={{fontSize:'0.65rem',color:'var(--text-muted)',marginBottom:4}}>{benchmarkCost.txPerHour[i]}</span>
                  <div style={{width:'100%',height:h,borderRadius:'6px 6px 0 0',background:isMAB?'var(--accent-green)':i===0?'var(--accent-red)':i===1?'var(--accent-amber)':'var(--accent-blue)',opacity:isMAB?1:0.6,transition:'height 600ms var(--ease-out)'}}/>
                  <span style={{fontSize:'0.6rem',color:isMAB?'var(--accent-green)':'var(--text-muted)',marginTop:6,textAlign:'center',fontWeight:isMAB?600:400}}>{f}</span>
                </div>
              );
            })}
          </div>
          <div style={{display:'flex',justifyContent:'center',gap:24,fontSize:'0.75rem',color:'var(--text-muted)'}}>
            <span>安全评分: {benchmarkCost.securityScore.map((s,i)=>(
              <span key={i} style={{marginLeft:8,color:i===4?'var(--accent-green)':'var(--text-secondary)'}}>{benchmarkCost.frequency[i].slice(0,4)}={s}</span>
            ))}</span>
          </div>
        </GlassCard>
      </section>

      {/* Performance Metrics */}
      <section className="section">
        <h3 style={{marginBottom:16,display:'flex',alignItems:'center',gap:10}}>
          <Clock size={18} className="text-blue" /> 性能指标
        </h3>
        <div className="grid-3">
          {performanceMetrics.map((m,i)=>(
            <GlassCard key={m.metric} glowColor="#3B82F6" className={`animate-fade-in-up stagger-${i+1}`}>
              <div style={{fontSize:'0.7rem',color:'var(--text-muted)',textTransform:'uppercase',letterSpacing:'0.04em'}}>{m.metric}</div>
              <div style={{fontSize:'1.6rem',fontWeight:700,fontFamily:'var(--font-display)',color:'var(--accent-blue)',margin:'8px 0'}}>
                {m.value}
              </div>
              <div style={{fontSize:'0.75rem',color:'var(--text-secondary)'}}>{m.detail}</div>
            </GlassCard>
          ))}
        </div>
      </section>
    </div>
  );
}
