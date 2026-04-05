import { useState } from 'react';
import Navbar from './components/Navbar';
import OverviewPage from './pages/OverviewPage';
import EdgePage from './pages/EdgePage';
import GatewayPage from './pages/GatewayPage';
import StoragePage from './pages/StoragePage';
import BlockchainPage from './pages/BlockchainPage';
import VerificationPage from './pages/VerificationPage';
import BenchmarkPage from './pages/BenchmarkPage';

const pages = {
  overview: OverviewPage,
  edge: EdgePage,
  gateway: GatewayPage,
  storage: StoragePage,
  blockchain: BlockchainPage,
  verification: VerificationPage,
  benchmark: BenchmarkPage,
};

export default function App() {
  const [activePage, setActivePage] = useState('overview');
  const PageComponent = pages[activePage] || OverviewPage;

  const handleNavigate = (pageId) => {
    setActivePage(pageId);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  return (
    <>
      {/* Subtle grid background */}
      <div className="grid-bg" />

      {/* Navigation */}
      <Navbar activePage={activePage} onNavigate={handleNavigate} />

      {/* Page content */}
      <main key={activePage} style={{ position: 'relative', zIndex: 1 }}>
        <PageComponent />
      </main>

      {/* Footer */}
      <footer style={{
        textAlign: 'center',
        padding: '32px 20px',
        borderTop: '1px solid var(--glass-border)',
        fontSize: '0.75rem',
        color: 'var(--text-muted)',
        position: 'relative',
        zIndex: 1,
      }}>
        <span style={{ fontFamily: 'var(--font-display)', fontWeight: 600, letterSpacing: '0.05em' }}>
          SecureLens
        </span>
        {' '} — 基于边缘 AI 与联盟链的监控视频防篡改系统 · 中国大学生计算机设计大赛
      </footer>
    </>
  );
}
