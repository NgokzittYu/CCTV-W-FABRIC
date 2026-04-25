import { useCallback, useState } from 'react';
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion';
import LoginPage from './pages/LoginPage';
import DashboardPage from './pages/DashboardPage';
import LiveMonitorPage from './pages/LiveMonitorPage';
import VideoEvidencePage from './pages/VideoEvidencePage';
import EvidencePage from './pages/EvidencePage';
import LedgerPage from './pages/LedgerPage';
import WorkorderPage from './pages/WorkorderPage';
import AnchorPage from './pages/AnchorPage';
import IPFSPage from './pages/IPFSPage';
import Sidebar from './components/Sidebar';

export default function App() {
  const [role, setRole] = useState(null);
  const [activeTab, setActiveTab] = useState('');
  const shouldReduceMotion = useReducedMotion();

  const handleLogin = useCallback((selectedRole) => {
    setRole(selectedRole);
    setActiveTab('dashboard');
  }, []);

  const handleLogout = useCallback(() => {
    setRole(null);
    setActiveTab('');
  }, []);

  if (!role) {
    return (
      <>
        <div className="grid-bg" />
        <LoginPage onLogin={handleLogin} />
      </>
    );
  }

  const renderPage = () => {
    switch (activeTab) {
      case 'dashboard':  return <DashboardPage />;
      case 'monitor':    return <LiveMonitorPage />;
      case 'video':      return role === 'admin' ? <DashboardPage /> : <VideoEvidencePage role={role} />;
      case 'evidence':   return role === 'admin' ? <DashboardPage /> : <EvidencePage />;
      case 'ledger':     return <LedgerPage />;
      case 'workorder':  return <WorkorderPage />;
      case 'anchor':     return <AnchorPage />;
      case 'ipfs':       return <IPFSPage />;
      default:           return <DashboardPage />;
    }
  };

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
          <AnimatePresence initial={false} mode="wait">
            <motion.div
              key={`${role}-${activeTab || 'dashboard'}`}
              className="app-pageTransition"
              initial={shouldReduceMotion ? { opacity: 0 } : { opacity: 0, transform: 'translateY(6px)' }}
              animate={
                shouldReduceMotion
                  ? {
                      opacity: 1,
                      transition: { duration: 0.12, ease: [0.2, 0, 0, 1] },
                    }
                  : {
                      opacity: 1,
                      transform: 'translateY(0px)',
                      transition: { duration: 0.16, ease: [0.23, 1, 0.32, 1] },
                    }
              }
              exit={
                shouldReduceMotion
                  ? {
                      opacity: 0,
                      transition: { duration: 0.08, ease: [0.2, 0, 0, 1] },
                    }
                  : {
                      opacity: 0,
                      transform: 'translateY(2px)',
                      transition: { duration: 0.08, ease: [0.2, 0, 0, 1] },
                    }
              }
            >
              {renderPage()}
            </motion.div>
          </AnimatePresence>
        </main>
      </div>
    </>
  );
}
