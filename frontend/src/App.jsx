import { useState } from 'react';
import './index.css';
import { ToastProvider } from './components';
import { Dashboard, Companies, Individuals } from './pages/Targets';
import { Generate, Drafts } from './pages/Emails';
import { Tracking, ReplyTracker } from './pages/Tracking';

const NAV = [
  { id: 'dashboard',   label: 'Dashboard',       icon: '🌿', section: 'OVERVIEW' },
  { id: 'companies',   label: 'Companies',        icon: '🏢', section: 'TARGETS' },
  { id: 'individuals', label: 'Individuals',      icon: '👤', section: 'TARGETS' },
  { id: 'generate',    label: 'Generate Email',   icon: '✨', section: 'OUTREACH' },
  { id: 'drafts',      label: 'Email Drafts',     icon: '📬', section: 'OUTREACH' },
  { id: 'tracking',    label: 'Tracking',         icon: '📊', section: 'FOLLOW-UP' },
  { id: 'replies',     label: 'Log Reply',        icon: '✍️', section: 'FOLLOW-UP' },
];

function App() {
  const [page, setPage] = useState('dashboard');

  const renderPage = () => {
    switch (page) {
      case 'dashboard':   return <Dashboard />;
      case 'companies':   return <Companies />;
      case 'individuals': return <Individuals />;
      case 'generate':    return <Generate />;
      case 'drafts':      return <Drafts />;
      case 'tracking':    return <Tracking />;
      case 'replies':     return <ReplyTracker />;
      default:            return <Dashboard />;
    }
  };

  const sections = [...new Set(NAV.map(n => n.section))];

  return (
    <ToastProvider>
      <div className="layout">
        {/* Sidebar */}
        <aside className="sidebar">
          <div className="sidebar-logo">
            <div className="logo-mark">
              <div className="logo-icon">🌱</div>
              <span>OutreachAI</span>
            </div>
          </div>

          <nav className="sidebar-nav">
            {sections.map(section => (
              <div key={section}>
                <div className="nav-section-label">{section}</div>
                {NAV.filter(n => n.section === section).map(item => (
                  <button
                    key={item.id}
                    className={`nav-item${page === item.id ? ' active' : ''}`}
                    onClick={() => setPage(item.id)}
                  >
                    <span className="nav-icon">{item.icon}</span>
                    <span>{item.label}</span>
                  </button>
                ))}
              </div>
            ))}
          </nav>

          <div className="sidebar-footer">
            <div style={{ marginBottom: 4, fontWeight: 600, color: 'var(--text-secondary)' }}>OutreachAI v0.1</div>
            <div>Animal advocacy email automation</div>
            <div style={{ marginTop: 8 }}>
              <a href="http://localhost:8000/docs" target="_blank" style={{ fontSize: '0.72rem', color: 'var(--accent-2)' }}>
                📖 API Docs
              </a>
            </div>
          </div>
        </aside>

        {/* Main Content */}
        <main className="main-content">
          {renderPage()}
        </main>
      </div>
    </ToastProvider>
  );
}

export default App;
