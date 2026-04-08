import { useState } from 'react';
import { Shield, ShieldCheck, User, Lock, ChevronRight, Eye } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

const roles = [
  {
    id: 'admin',
    title: '管理方',
    subtitle: '监控管理 · 视频存证 · 链上锚定',
    icon: Shield,
    color: 'var(--accent-green)',
    dimColor: 'var(--accent-green-dim)',
    username: 'admin',
    password: 'admin123',
  },
  {
    id: 'verifier',
    title: '验证方',
    subtitle: '证据验真 · 完整性校验 · 报告生成',
    icon: ShieldCheck,
    color: 'var(--accent-purple)',
    dimColor: 'var(--accent-purple-dim)',
    username: 'verifier',
    password: 'verify123',
  },
];

export default function LoginPage({ onLogin }) {
  const [selectedRole, setSelectedRole] = useState(null);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const handleSelectRole = (role) => {
    setSelectedRole(role);
    setUsername(role.username);
    setPassword(role.password);
    setError('');
  };

  const handleLogin = async (e) => {
    e.preventDefault();
    if (!selectedRole) {
      setError('请选择登录角色');
      return;
    }
    setIsLoading(true);
    // Simulate authentication delay
    await new Promise((r) => setTimeout(r, 600));
    setIsLoading(false);
    onLogin(selectedRole.id);
  };

  return (
    <div className="login-page">
      {/* Animated background particles */}
      <div className="login-bg-particles">
        {[...Array(6)].map((_, i) => (
          <div key={i} className="particle" style={{ '--i': i }} />
        ))}
      </div>

      <motion.div
        className="login-container"
        initial={{ opacity: 0, y: 30 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, ease: [0.23, 1, 0.32, 1] }}
      >
        {/* Logo */}
        <div className="login-logo">
          <div className="login-logo-icon">
            <Shield size={28} />
          </div>
          <h1 className="login-title">SecureLens</h1>
          <p className="login-subtitle">
            基于边缘 AI 与联盟链的监控视频防篡改系统
          </p>
        </div>

        {/* Role Selection */}
        <div className="login-roles">
          {roles.map((role) => {
            const Icon = role.icon;
            const isSelected = selectedRole?.id === role.id;
            return (
              <motion.button
                key={role.id}
                className={`role-card ${isSelected ? 'role-card--active' : ''}`}
                onClick={() => handleSelectRole(role)}
                whileTap={{ scale: 0.97 }}
                style={{
                  '--role-color': role.color,
                  '--role-dim': role.dimColor,
                }}
              >
                <div className="role-card-icon">
                  <Icon size={22} />
                </div>
                <div className="role-card-text">
                  <span className="role-card-title">{role.title}</span>
                  <span className="role-card-sub">{role.subtitle}</span>
                </div>
                <ChevronRight size={16} className="role-card-arrow" />
              </motion.button>
            );
          })}
        </div>

        {/* Login Form */}
        <AnimatePresence>
          {selectedRole && (
            <motion.form
              className="login-form"
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
              transition={{ duration: 0.35, ease: [0.23, 1, 0.32, 1] }}
              onSubmit={handleLogin}
            >
              <div className="login-field">
                <User size={16} className="login-field-icon" />
                <input
                  type="text"
                  placeholder="用户名"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  id="login-username"
                />
              </div>
              <div className="login-field">
                <Lock size={16} className="login-field-icon" />
                <input
                  type={showPassword ? 'text' : 'password'}
                  placeholder="密码"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  id="login-password"
                />
                <button
                  type="button"
                  className="login-field-toggle"
                  onClick={() => setShowPassword(!showPassword)}
                >
                  <Eye size={14} />
                </button>
              </div>

              {error && <p className="login-error">{error}</p>}

              <button
                type="submit"
                className="login-submit"
                disabled={isLoading}
                style={{ '--role-color': selectedRole.color }}
              >
                {isLoading ? (
                  <span className="login-spinner" />
                ) : (
                  <>登录</>
                )}
              </button>

              <p className="login-hint">
                演示模式：已预填账号密码，直接点击登录即可
              </p>
            </motion.form>
          )}
        </AnimatePresence>
      </motion.div>

      {/* Footer */}
      <div className="login-footer">
        <span className="font-display" style={{ fontWeight: 600, letterSpacing: '0.05em' }}>
          SecureLens
        </span>
        {' '}— 中国大学生计算机设计大赛
      </div>
    </div>
  );
}
