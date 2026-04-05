import { useState } from 'react';
import { Link, Server, FileCode, Clock, CheckCircle, ShieldCheck, Eye, ArrowRight, Hash } from 'lucide-react';
import GlassCard from '../components/GlassCard';
import { fabricNetwork, smartContractFunctions, blockchainTransactions } from '../data/mockData';

export default function BlockchainPage() {
  const [selectedTx, setSelectedTx] = useState(null);
  const [anchorDemo, setAnchorDemo] = useState('idle');

  const simulateAnchor = () => {
    setAnchorDemo('anchoring');
    setTimeout(() => setAnchorDemo('verifying'), 1200);
    setTimeout(() => setAnchorDemo('done'), 2200);
  };

  return (
    <div className="page-container">
      <div className="section-header">
        <h2 className="section-title"><Link size={24} className="text-amber" /> Hyperledger Fabric 联盟链</h2>
        <p className="section-subtitle">3 组织 × 2 Peer 联盟网络，智能合约实现 EpochRoot 锚定与 Merkle 验证</p>
      </div>

      {/* Network Topology */}
      <section className="section">
        <h3 className="sub-heading"><Server size={18} className="text-purple" /> 网络拓扑</h3>
        <div className="grid-3">
          {fabricNetwork.orgs.map((org, i) => (
            <GlassCard key={org.name} glowColor={org.color} className={`animate-fade-in-up stagger-${i+1}`}>
              <div style={{marginBottom:8}}><span style={{fontFamily:'var(--font-display)',fontSize:'0.9rem',fontWeight:600,color:org.color}}>{org.name}</span></div>
              <p style={{fontSize:'0.8rem',marginBottom:12}}>{org.role}</p>
              <div style={{display:'flex',flexDirection:'column',gap:6}}>
                {org.peers.map(p=>(
                  <div key={p} style={{display:'flex',alignItems:'center',gap:8,padding:'6px 12px',borderRadius:6,background:'var(--bg-secondary)',fontSize:'0.75rem',fontFamily:'monospace',color:'var(--text-secondary)'}}>
                    <Server size={12}/>{p}
                  </div>
                ))}
              </div>
            </GlassCard>
          ))}
        </div>
        <div style={{display:'flex',alignItems:'center',gap:16,marginTop:16,padding:'12px 20px',borderRadius:10,background:'var(--glass-bg)',border:'1px solid var(--glass-border)',fontSize:'0.8rem',flexWrap:'wrap'}}>
          <span style={{fontWeight:600,color:'var(--accent-amber)',fontSize:'0.7rem',textTransform:'uppercase',letterSpacing:'0.04em'}}>Orderer</span>
          <code style={{color:'var(--text-secondary)'}}>{fabricNetwork.orderer}</code>
          <span style={{color:'var(--text-muted)'}}>Channel: <strong>{fabricNetwork.channel}</strong></span>
        </div>
      </section>

      {/* Smart Contract */}
      <section className="section">
        <h3 className="sub-heading"><FileCode size={18} className="text-green" /> 智能合约 (Go Chaincode)</h3>
        <div className="grid-2">
          {smartContractFunctions.map((fn,i)=>(
            <GlassCard key={fn.name} glowColor={fn.name==='Anchor'?'#F59E0B':fn.name==='VerifyAnchor'?'#22C55E':'#3B82F6'} className={`animate-fade-in-up stagger-${i+1}`}>
              <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',marginBottom:8}}>
                <code style={{color:'var(--accent-green)',fontSize:'0.9rem',fontWeight:600}}>{fn.name}()</code>
                <span style={{fontSize:'0.65rem',padding:'2px 8px',borderRadius:10,background:'var(--bg-secondary)',color:'var(--text-muted)'}}>{fn.access}</span>
              </div>
              <p style={{fontSize:'0.8rem',marginBottom:12}}>{fn.desc}</p>
              <div style={{display:'flex',gap:6,flexWrap:'wrap'}}>
                {fn.params.map(p=>(<span key={p} style={{padding:'2px 8px',borderRadius:4,background:'var(--accent-blue-dim)',color:'var(--accent-blue)',fontSize:'0.7rem',fontFamily:'monospace'}}>{p}</span>))}
              </div>
            </GlassCard>
          ))}
        </div>
      </section>

      {/* Anchor Demo */}
      <section className="section">
        <h3 className="sub-heading"><ShieldCheck size={18} className="text-cyan" /> 锚定 & 验证演示</h3>
        <GlassCard hover={false}>
          <button className="btn btn-primary" onClick={simulateAnchor} disabled={anchorDemo!=='idle'&&anchorDemo!=='done'}>
            {anchorDemo==='idle'||anchorDemo==='done'?'执行 Anchor → VerifyAnchor':'处理中...'}
          </button>
          <div style={{display:'flex',alignItems:'center',gap:16,marginTop:24,flexWrap:'wrap'}}>
            {[
              {key:'anchoring',icon:Hash,title:'Anchor()',desc:'EpochRoot 上链',color:'var(--accent-amber)',active:anchorDemo==='anchoring'||anchorDemo==='verifying'||anchorDemo==='done',done:anchorDemo==='verifying'||anchorDemo==='done',loading:anchorDemo==='anchoring'},
              {key:'verifying',icon:ShieldCheck,title:'VerifyAnchor()',desc:'Merkle Proof 验证',color:'var(--accent-green)',active:anchorDemo==='verifying'||anchorDemo==='done',done:anchorDemo==='done',loading:anchorDemo==='verifying'},
              {key:'result',icon:Eye,title:'结果',desc:anchorDemo==='done'?'✓ INTACT — 验证通过':'等待验证',color:'var(--accent-green)',active:anchorDemo==='done',done:false,loading:false},
            ].map((s,i)=>(
              <div key={s.key} style={{display:'flex',alignItems:'center',gap:12}}>
                <div style={{display:'flex',alignItems:'center',gap:12,padding:'16px 20px',borderRadius:12,background:'var(--bg-secondary)',border:`1px solid ${s.active?'var(--accent-green)':'var(--border-color)'}`,opacity:s.active?1:0.4,transition:'all 400ms cubic-bezier(0.23,1,0.32,1)'}}>
                  <div style={{width:40,height:40,borderRadius:10,display:'flex',alignItems:'center',justifyContent:'center',background:s.active?`${s.color}15`:'var(--bg-card)',color:s.active?s.color:'var(--text-muted)'}}>
                    <s.icon size={18}/>
                  </div>
                  <div>
                    <div style={{fontWeight:600,fontSize:'0.85rem'}}>{s.title}</div>
                    <div style={{fontSize:'0.75rem',color:s.done||s.key==='result'&&anchorDemo==='done'?'var(--accent-green)':'var(--text-muted)',marginTop:2,fontWeight:s.key==='result'&&anchorDemo==='done'?600:400}}>{s.desc}</div>
                  </div>
                  {s.loading&&<div style={{width:16,height:16,border:'2px solid var(--border-color)',borderTopColor:'var(--accent-green)',borderRadius:'50%',animation:'spin-slow 0.8s linear infinite'}}/>}
                  {s.done&&<CheckCircle size={16} className="text-green"/>}
                </div>
                {i<2&&<ArrowRight size={20} className="text-muted"/>}
              </div>
            ))}
          </div>
        </GlassCard>
      </section>

      {/* Tx Explorer */}
      <section className="section">
        <h3 className="sub-heading"><Clock size={18} className="text-blue" /> 交易记录</h3>
        <GlassCard hover={false}>
          {blockchainTransactions.map((tx,i)=>(
            <div key={i} onClick={()=>setSelectedTx(selectedTx===i?null:i)} style={{display:'flex',alignItems:'center',gap:16,padding:'10px 14px',borderRadius:8,cursor:'pointer',background:selectedTx===i?'var(--accent-purple-dim)':'transparent',transition:'background 200ms ease',flexWrap:'wrap',marginBottom:2}}>
              <span style={{padding:'3px 10px',borderRadius:6,fontSize:'0.7rem',fontWeight:600,minWidth:100,textAlign:'center',background:tx.function==='Anchor'?'var(--accent-amber-dim)':tx.function==='VerifyAnchor'?'var(--accent-green-dim)':'var(--accent-blue-dim)',color:tx.function==='Anchor'?'var(--accent-amber)':tx.function==='VerifyAnchor'?'var(--accent-green)':'var(--accent-blue)'}}>{tx.function}</span>
              <code style={{flex:1,fontSize:'0.72rem',color:'var(--text-muted)',minWidth:160}}>{tx.txId.slice(0,16)}...{tx.txId.slice(-8)}</code>
              <span style={{fontSize:'0.75rem',color:'var(--text-secondary)'}}>{new Date(tx.timestamp).toLocaleTimeString('zh-CN')}</span>
              <span style={{fontSize:'0.72rem',color:'var(--text-muted)',minWidth:70}}>{tx.signerMSP}</span>
              <span style={{display:'flex',alignItems:'center',gap:4,fontSize:'0.7rem',fontWeight:600,color:'var(--accent-green)'}}><CheckCircle size={12}/>{tx.status}</span>
            </div>
          ))}
        </GlassCard>
      </section>

      <style>{`
        .sub-heading{margin-bottom:16px;display:flex;align-items:center;gap:10px;}
      `}</style>
    </div>
  );
}
