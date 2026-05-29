import { useState } from 'react';
import './index.css';
import { ToastProvider } from './components';
import { Dashboard, Companies, Individuals } from './pages/Targets';
import { Generate, Campaigns } from './pages/Emails';
import { Tracking, ReplyTracker } from './pages/Tracking';

const NAV = [
  { id: 'dashboard',   label: 'Dashboard',       icon: '🌿', section: 'OVERVIEW' },
  { id: 'companies',   label: 'Companies',        icon: '🏢', section: 'TARGETS' },
  { id: 'individuals', label: 'Individuals',      icon: '👤', section: 'TARGETS' },
  { id: 'generate',    label: 'Generate Email',   icon: '✨', section: 'OUTREACH' },
  { id: 'campaigns',   label: 'Campaigns',        icon: '🗂️', section: 'OUTREACH' },
  { id: 'tracking',    label: 'Tracking',         icon: '📊', section: 'FOLLOW-UP' },
  { id: 'replies',     label: 'Log Reply',        icon: '✍️', section: 'FOLLOW-UP' },
];

function App() {
  const [page, setPage] = useState('dashboard');
  const [pageProps, setPageProps] = useState({});

  const navigate = (id, props = {}) => {
    setPage(id);
    setPageProps(props);
  };

  // Pages are now rendered persistently below to prevent unmounting and cancelling background tasks.
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
                    onClick={() => navigate(item.id)}
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
          <div style={{ display: page === 'dashboard' ? 'block' : 'none' }}><Dashboard navigate={navigate} /></div>
          <div style={{ display: page === 'companies' ? 'block' : 'none' }}><Companies navigate={navigate} /></div>
          <div style={{ display: page === 'individuals' ? 'block' : 'none' }}><Individuals navigate={navigate} /></div>
          <div style={{ display: page === 'generate' ? 'block' : 'none' }}><Generate navigate={navigate} /></div>
          <div style={{ display: page === 'campaigns' ? 'block' : 'none' }}><Campaigns {...pageProps} navigate={navigate} /></div>
          <div style={{ display: page === 'tracking' ? 'block' : 'none' }}><Tracking navigate={navigate} /></div>
          <div style={{ display: page === 'replies' ? 'block' : 'none' }}><ReplyTracker navigate={navigate} /></div>
        </main>
      </div>
    </ToastProvider>
  );
}

export default App;
