import {
  Brain, Network, HardDrive, Link, Shield, Eye,
  BarChart3, ChevronRight, Scan
} from 'lucide-react';

const NAV_ITEMS = [
  { id: 'overview', label: '系统概览', icon: Eye },
  { id: 'edge', label: '边缘智能', icon: Brain },
  { id: 'gateway', label: '聚合网关', icon: Network },
  { id: 'storage', label: 'IPFS 存储', icon: HardDrive },
  { id: 'blockchain', label: '联盟链', icon: Link },
  { id: 'verification', label: '审计验证', icon: Shield },
  { id: 'benchmark', label: '对比实验', icon: BarChart3 },
];

export default function Navbar({ activePage, onNavigate }) {
  return (
    <nav className="navbar">
      <div className="navbar-inner">
        <div className="navbar-brand" onClick={() => onNavigate('overview')}>
          <Scan size={24} className="text-green" />
          <span className="brand-text">SecureLens</span>
        </div>

        <div className="navbar-links">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            const isActive = activePage === item.id;
            return (
              <button
                key={item.id}
                className={`nav-link ${isActive ? 'active' : ''}`}
                onClick={() => onNavigate(item.id)}
              >
                <Icon size={16} />
                <span className="nav-label">{item.label}</span>
                {isActive && <div className="nav-indicator" />}
              </button>
            );
          })}
        </div>

        <div className="navbar-badge">
          <span className="competition-badge">计算机设计大赛</span>
        </div>
      </div>

      <style>{`
        .navbar {
          position: fixed;
          top: 0;
          left: 0;
          right: 0;
          z-index: 100;
          background: rgba(2, 6, 23, 0.75);
          backdrop-filter: blur(20px);
          -webkit-backdrop-filter: blur(20px);
          border-bottom: 1px solid var(--glass-border);
        }
        .navbar-inner {
          max-width: 1400px;
          margin: 0 auto;
          height: var(--nav-height);
          display: flex;
          align-items: center;
          padding: 0 20px;
          gap: 8px;
        }
        .navbar-brand {
          display: flex;
          align-items: center;
          gap: 10px;
          cursor: pointer;
          flex-shrink: 0;
          margin-right: 16px;
          transition: transform 160ms cubic-bezier(0.23, 1, 0.32, 1);
        }
        .navbar-brand:active {
          transform: scale(0.97);
        }
        .brand-text {
          font-family: var(--font-display);
          font-weight: 700;
          font-size: 1.1rem;
          letter-spacing: 0.05em;
          background: linear-gradient(135deg, var(--accent-green), var(--accent-cyan));
          -webkit-background-clip: text;
          -webkit-text-fill-color: transparent;
          background-clip: text;
        }
        .navbar-links {
          display: flex;
          align-items: center;
          gap: 2px;
          flex: 1;
          justify-content: center;
          overflow-x: auto;
          scrollbar-width: none;
        }
        .navbar-links::-webkit-scrollbar { display: none; }

        .nav-link {
          position: relative;
          display: flex;
          align-items: center;
          gap: 6px;
          padding: 8px 12px;
          border: none;
          background: none;
          color: var(--text-muted);
          font-family: var(--font-body);
          font-size: 0.8rem;
          font-weight: 500;
          cursor: pointer;
          border-radius: 8px;
          white-space: nowrap;
          transition:
            color 200ms ease,
            background 200ms ease,
            transform 160ms cubic-bezier(0.23, 1, 0.32, 1);
        }
        .nav-link:hover {
          color: var(--text-secondary);
          background: rgba(148, 163, 184, 0.06);
        }
        .nav-link:active {
          transform: scale(0.97);
        }
        .nav-link.active {
          color: var(--text-primary);
          background: rgba(139, 92, 246, 0.1);
        }
        .nav-indicator {
          position: absolute;
          bottom: 0;
          left: 50%;
          transform: translateX(-50%);
          width: 20px;
          height: 2px;
          background: var(--accent-purple);
          border-radius: 1px;
        }
        .navbar-badge {
          flex-shrink: 0;
          margin-left: 12px;
        }
        .competition-badge {
          padding: 4px 12px;
          border-radius: 20px;
          font-size: 0.7rem;
          font-weight: 600;
          background: var(--accent-purple-dim);
          color: var(--accent-purple);
          border: 1px solid rgba(139, 92, 246, 0.3);
          letter-spacing: 0.04em;
        }
        @media (max-width: 1024px) {
          .nav-label { display: none; }
          .nav-link { padding: 8px; }
          .competition-badge { display: none; }
        }
      `}</style>
    </nav>
  );
}

export { NAV_ITEMS };
