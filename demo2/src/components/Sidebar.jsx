import {
  Activity, Video, Blocks, AlertTriangle,
  LogOut, TerminalSquare, Brain, Database, ShieldCheck, FileSearch
} from 'lucide-react';
import { motion } from 'framer-motion';

const adminTabs = [
  { id: 'dashboard', label: '仪表盘', icon: Activity },
  { id: 'monitor', label: '实时监控', icon: Video },
  { id: 'ipfs', label: 'IPFS 存储', icon: Database },
  { id: 'anchor', label: '智能锚定', icon: Brain },
  { id: 'ledger', label: '区块链', icon: Blocks },
  { id: 'workorder', label: '告警与工单', icon: AlertTriangle },
];

const verifierTabs = [
  { id: 'dashboard', label: '仪表盘', icon: Activity },
  { id: 'video', label: '视频证据', icon: ShieldCheck },
  { id: 'anchor', label: '智能锚定', icon: Brain },
  { id: 'ledger', label: '区块链账本', icon: Blocks },
  { id: 'ipfs', label: 'IPFS 存储', icon: Database },
  { id: 'evidence', label: '证据浏览', icon: FileSearch },
];

export default function Sidebar({ role, activeTab, onTabChange, onLogout }) {
  const tabs = role === 'admin' ? adminTabs : verifierTabs;
  const roleLabel = role === 'admin' ? '管理终端' : '验证终端';

  return (
    <aside className="sidebar-shell">
      <div className="sidebar-brand">
        <div className="sidebar-brand__identity">
          <div className="sidebar-brand__mark">
            <TerminalSquare size={18} />
          </div>
          <div>
            <div className="sidebar-brand__name">SECURELENS</div>
          </div>
        </div>

        <div className="sidebar-brand__meta">
          <span className="sidebar-brand__metaLabel">当前角色</span>
          <strong>{roleLabel}</strong>
        </div>
      </div>

      <nav className="sidebar-nav">
        {tabs.map((tab) => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              type="button"
              onClick={() => onTabChange(tab.id)}
              className={`sidebar-nav__item${isActive ? ' is-active' : ''}`}
            >
              {isActive && (
                <motion.div
                  layoutId="sidebar-indicator"
                  transition={{ type: 'spring', stiffness: 400, damping: 30 }}
                  className="sidebar-nav__indicator"
                />
              )}

              <span className="sidebar-nav__icon">
                <Icon size={17} />
              </span>
              <span className="sidebar-nav__content">
                <span className="sidebar-nav__label">{tab.label}</span>
              </span>
            </button>
          );
        })}
      </nav>

      <div className="sidebar-footer">
        <button type="button" onClick={onLogout} className="sidebar-logout">
          <LogOut size={16} />
          <span>终止会话</span>
        </button>
      </div>
    </aside>
  );
}
