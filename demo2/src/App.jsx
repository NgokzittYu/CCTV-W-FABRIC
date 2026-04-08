import { useState, useCallback } from 'react';
import LoginPage from './pages/LoginPage';
import AdminDashboard from './pages/AdminDashboard';
import VerifyPortal from './pages/VerifyPortal';
import Sidebar from './components/Sidebar';

export default function App() {
  const [role, setRole] = useState(null);          // null | 'admin' | 'verifier'
  const [activeTab, setActiveTab] = useState('');   // current sidebar tab

  const handleLogin = useCallback((selectedRole) => {
    setRole(selectedRole);
    setActiveTab(selectedRole === 'admin' ? 'overview' : 'verify');
  }, []);

  const handleLogout = useCallback(() => {
    setRole(null);
    setActiveTab('');
  }, []);

  // ── Login Screen ──
  if (!role) {
    return (
      <>
        <div className="grid-bg" />
        <LoginPage onLogin={handleLogin} />
      </>
    );
  }

  // ── Dashboard / Portal ──
  return (
    <>
      <div className="grid-bg" />
      <div className="app-layout">
        <Sidebar
          role={role}
          activeTab={activeTab}
          onTabChange={setActiveTab}
          onLogout={handleLogout}
        />
        <main className="app-main">
          {role === 'admin' ? (
            <AdminDashboard activeTab={activeTab} />
          ) : (
            <VerifyPortal activeTab={activeTab} />
          )}
        </main>
      </div>
    </>
  );
}
