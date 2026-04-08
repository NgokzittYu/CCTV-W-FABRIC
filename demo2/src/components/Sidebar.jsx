import {
  LayoutDashboard, HardDrive, Video, AlertTriangle,
  ShieldCheck, FileText, History, LogOut
} from 'lucide-react';
import { motion } from 'framer-motion';

const adminTabs = [
  { id: 'overview', label: '监控总览', icon: LayoutDashboard },
  { id: 'devices',  label: '设备管理', icon: HardDrive },
  { id: 'archive',  label: '视频存证', icon: Video },
  { id: 'alerts',   label: '告警中心', icon: AlertTriangle },
];

const verifierTabs = [
  { id: 'verify',   label: '证据验真', icon: ShieldCheck },
  { id: 'report',   label: '验真报告', icon: FileText },
  { id: 'history',  label: '历史记录', icon: History },
];

export default function Sidebar({ role, activeTab, onTabChange, onLogout }) {
  const tabs = role === 'admin' ? adminTabs : verifierTabs;
  const roleLabel = role === 'admin' ? '管理后台' : '验证平台';
  const roleColor = role === 'admin' ? 'var(--accent-green)' : 'var(--accent-purple)';

  return (
    <aside className="sidebar">
      {/* Brand */}
      <div className="sidebar-brand">
        <div className="sidebar-brand-logo" style={{ color: roleColor }}>
          <ShieldCheck size={24} />
        </div>
        <div className="sidebar-brand-text">
          <span className="sidebar-brand-name">SecureLens</span>
          <span className="sidebar-brand-role" style={{ color: roleColor }}>
            {roleLabel}
          </span>
        </div>
      </div>

      {/* Navigation */}
      <nav className="sidebar-nav">
        {tabs.map((tab) => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              className={`sidebar-item ${isActive ? 'sidebar-item--active' : ''}`}
              onClick={() => onTabChange(tab.id)}
              style={{ '--tab-color': roleColor }}
            >
              {isActive && (
                <motion.div
                  className="sidebar-item-bg"
                  layoutId="sidebar-active"
                  transition={{ type: 'spring', stiffness: 350, damping: 30 }}
                  style={{ background: roleColor + '15' }}
                />
              )}
              <Icon size={18} />
              <span>{tab.label}</span>
              {isActive && (
                <div className="sidebar-item-indicator" style={{ background: roleColor }} />
              )}
            </button>
          );
        })}
      </nav>

      {/* Footer */}
      <div className="sidebar-footer">
        <button className="sidebar-logout" onClick={onLogout}>
          <LogOut size={16} />
          <span>退出登录</span>
        </button>
      </div>
    </aside>
  );
}
