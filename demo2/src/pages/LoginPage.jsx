import { useState, useEffect } from 'react';
import { Shield, Terminal, ArrowRight, Eye, KeyRound } from 'lucide-react';

const roles = [
  { id: 'admin', title: '管理终端', access: '节点控制与链上锚定', username: 'admin', password: 'admin123' },
  { id: 'verifier', title: '验证终端', access: '证据核验与 VIF 报告', username: 'verifier', password: 'verify123' },
];

export default function LoginPage({ onLogin }) {
  const [selectedRole, setSelectedRole] = useState(null);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [logs, setLogs] = useState(['控制平面已就绪，等待身份选择']);
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    const bootSequence = [
      'Fabric 读链连接正常',
      'IPFS 仓库响应正常',
      'VIF 检测服务已加载',
      '等待用户身份授权',
    ];
    let delayMs = 0;
    const timers = [];

    bootSequence.forEach((log) => {
      delayMs += 420;
      timers.push(setTimeout(() => setLogs((prev) => [...prev, log]), delayMs));
    });

    return () => timers.forEach((timer) => clearTimeout(timer));
  }, []);

  const handleSelectRole = (role) => {
    setSelectedRole(role);
    setUsername(role.username);
    setPassword(role.password);
    setLogs((prev) => [...prev, `已选择 ${role.title}`]);
  };

  const handleLogin = async (e) => {
    e.preventDefault();
    if (!selectedRole) {
      setLogs((prev) => [...prev, '未选择终端身份']);
      return;
    }
    setIsLoading(true);
    setLogs((prev) => [...prev, `正在校验 ${selectedRole.title} 凭据`]);

    await new Promise((resolve) => setTimeout(resolve, 800));
    setLogs((prev) => [...prev, '凭据校验通过，正在载入控制台']);

    await new Promise((resolve) => setTimeout(resolve, 400));
    onLogin(selectedRole.id);
  };

  return (
    <div className="login-shell">
      <div className="scan-overlay" />

      <section className="tech-panel anim-enter login-frame">
        <header className="login-frame__header">
          <div className="login-frame__titleWrap">
            <div className="login-frame__mark">
              <Terminal size={28} />
            </div>
            <div>
              <h1 className="login-frame__title">SECURELENS 监控系统</h1>
            </div>
          </div>

          <div className="login-frame__signals">
            <div className="login-frame__signal">
              <span>Fabric</span>
              <strong>在线</strong>
            </div>
            <div className="login-frame__signal">
              <span>IPFS</span>
              <strong>可用</strong>
            </div>
            <div className="login-frame__signal">
              <span>VIF</span>
              <strong>已加载</strong>
            </div>
          </div>
        </header>

        <div className="login-frame__body">
          <div className="login-panel login-panel--auth">
            <div className="login-section">
              <span className="dashboard-eyebrow">选择终端身份</span>
              <div className="login-roleGrid">
                {roles.map((role) => (
                  <button
                    key={role.id}
                    type="button"
                    onClick={() => handleSelectRole(role)}
                    className={`login-roleCard${selectedRole?.id === role.id ? ' is-active' : ''}`}
                  >
                    <div className="login-roleCard__copy">
                      <strong>{role.title}</strong>
                      <span>{role.access}</span>
                    </div>
                    <Shield size={18} />
                  </button>
                ))}
              </div>
            </div>

            <div className={`login-section login-auth${selectedRole ? '' : ' is-disabled'}`}>
              <span className="dashboard-eyebrow">凭据验证</span>
              <form onSubmit={handleLogin} className="login-form">
                <label className="login-field">
                  <Terminal size={16} className="login-field__icon" />
                  <input
                    className="input-raw login-field__input"
                    type="text"
                    placeholder="环境账户"
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                  />
                </label>

                <label className="login-field">
                  <KeyRound size={16} className="login-field__icon" />
                  <input
                    className="input-raw login-field__input"
                    type={showPassword ? 'text' : 'password'}
                    placeholder="安全密钥"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                  />
                  <button
                    type="button"
                    className="login-field__toggle"
                    onClick={() => setShowPassword(!showPassword)}
                  >
                    <Eye size={18} />
                  </button>
                </label>

                <button type="submit" className="btn btn-primary login-submit" disabled={isLoading}>
                  {isLoading ? '正在进入控制台' : '进入控制台'}
                  <ArrowRight size={18} />
                </button>
              </form>
            </div>
          </div>

          <aside className="login-panel login-panel--status">
            <div className="login-statusFeed">
              <span className="dashboard-eyebrow">系统状态</span>
              <div className="terminal-block login-terminal">
                {logs.map((log, index) => (
                  <div key={`${log}-${index}`} className="terminal-line">
                    {log}
                  </div>
                ))}
              </div>
            </div>
          </aside>
        </div>
      </section>
    </div>
  );
}
