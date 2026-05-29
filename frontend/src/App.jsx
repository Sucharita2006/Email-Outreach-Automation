import { useState } from 'react';
import './index.css';
import { ToastProvider } from './components';
import { Dashboard, Companies, Individuals } from './pages/Targets';
import { Generate, Campaigns } from './pages/Emails';
import { Tracking, ReplyTracker } from './pages/Tracking';
import { Sidebar } from '@/components/ui/modern-side-bar';

import { HeroGeometric } from '@/components/ui/shape-landing-hero';

function App() {
  const [page, setPage] = useState('landing');
  const [pageProps, setPageProps] = useState({});

  const navigate = (id, props = {}) => {
    setPage(id);
    setPageProps(props);
  };

  if (page === 'landing') {
    return <HeroGeometric onEnter={() => navigate('dashboard')} />;
  }

  return (
    <ToastProvider>
      <Sidebar activeItem={page} onNavigate={navigate}>
        <div style={{ display: page === 'dashboard' ? 'flex' : 'none', flex: 1, height: '100%', flexDirection: 'column' }}><Dashboard navigate={navigate} {...pageProps} /></div>
        <div style={{ display: page === 'companies' ? 'flex' : 'none', flex: 1, height: '100%', flexDirection: 'column' }}><Companies navigate={navigate} {...pageProps} /></div>
        <div style={{ display: page === 'individuals' ? 'flex' : 'none', flex: 1, height: '100%', flexDirection: 'column' }}><Individuals navigate={navigate} {...pageProps} /></div>
        
        <div style={{ display: page === 'generate' ? 'flex' : 'none', flex: 1, height: '100%', flexDirection: 'column' }}><Generate navigate={navigate} {...pageProps} /></div>
        <div style={{ display: page === 'campaigns' ? 'flex' : 'none', flex: 1, height: '100%', flexDirection: 'column' }}><Campaigns navigate={navigate} {...pageProps} /></div>
        
        <div style={{ display: page === 'tracking' ? 'flex' : 'none', flex: 1, height: '100%', flexDirection: 'column' }}><Tracking navigate={navigate} {...pageProps} /></div>
        <div style={{ display: page === 'replies' ? 'flex' : 'none', flex: 1, height: '100%', flexDirection: 'column' }}><ReplyTracker navigate={navigate} {...pageProps} /></div>
      </Sidebar>
    </ToastProvider>
  );
}

export default App;
