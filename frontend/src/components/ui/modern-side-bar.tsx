import React, { useState, useEffect } from 'react';
import { 
  Home, 
  Building, 
  Users, 
  PenTool, 
  Briefcase, 
  BarChart3, 
  MessageSquare,
  Menu, 
  X, 
  ChevronLeft, 
  ChevronRight,
  PawPrint,
} from 'lucide-react';

interface NavigationItem {
  id: string;
  name: string;
  icon: React.ComponentType<{ className?: string }>;
  section: string;
}

const navigationItems: NavigationItem[] = [
  { id: 'dashboard',   name: 'Dashboard',       icon: Home,          section: 'OVERVIEW' },
  { id: 'companies',   name: 'Companies',       icon: Building,      section: 'TARGETS' },
  { id: 'individuals', name: 'Individuals',     icon: Users,         section: 'TARGETS' },
  { id: 'generate',    name: 'Start Campaign',  icon: PenTool,       section: 'OUTREACH' },
  { id: 'campaigns',   name: 'Campaigns',       icon: Briefcase,     section: 'OUTREACH' },
  { id: 'tracking',    name: 'Tracking',        icon: BarChart3,     section: 'FOLLOW-UP' },
  { id: 'replies',     name: 'Log Reply',       icon: MessageSquare, section: 'FOLLOW-UP' },
];

interface SidebarProps {
  className?: string;
  activeItem: string;
  onNavigate: (id: string) => void;
  children: React.ReactNode;
}

export function Sidebar({ className = "", activeItem, onNavigate, children }: SidebarProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [isCollapsed, setIsCollapsed] = useState(false);

  // Auto-open sidebar on desktop
  useEffect(() => {
    const handleResize = () => {
      if (window.innerWidth >= 768) {
        setIsOpen(true);
      } else {
        setIsOpen(false);
      }
    };
    
    handleResize();
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  const toggleSidebar = () => setIsOpen(!isOpen);
  const toggleCollapse = () => setIsCollapsed(!isCollapsed);

  const handleItemClick = (itemId: string) => {
    onNavigate(itemId);
    if (window.innerWidth < 768) {
      setIsOpen(false);
    }
  };

  const sections = [...new Set(navigationItems.map(n => n.section))];

  return (
    <div className="flex min-h-screen w-full" style={{ background: 'var(--bg-primary)' }}>
      {/* Mobile hamburger button */}
      <button
        onClick={toggleSidebar}
        className="fixed top-4 left-4 z-50 p-2 rounded-lg shadow-md md:hidden transition-all duration-200"
        style={{ background: 'var(--bg-secondary)', border: '1px solid var(--border)', cursor: 'pointer' }}
        aria-label="Toggle sidebar"
      >
        {isOpen ? 
          <X className="h-5 w-5" style={{ color: 'var(--text-primary)' }} /> : 
          <Menu className="h-5 w-5" style={{ color: 'var(--text-primary)' }} />
        }
      </button>

      {/* Mobile overlay */}
      {isOpen && (
        <div 
          className="fixed inset-0 bg-black/40 backdrop-blur-sm z-30 md:hidden transition-opacity duration-300" 
          onClick={toggleSidebar} 
        />
      )}

      {/* Sidebar */}
      <div
        className={`
          fixed top-0 left-0 h-full z-40 transition-all duration-300 ease-in-out flex flex-col
          ${isOpen ? "translate-x-0" : "-translate-x-full"}
          ${isCollapsed ? "w-20" : "w-64"}
          md:translate-x-0 md:static
          ${className}
        `}
        style={{ background: 'var(--bg-secondary)', borderRight: '1px solid var(--border)' }}
      >
        {/* Header with logo and collapse button */}
        <div className="flex items-center justify-between p-5" style={{ borderBottom: '1px solid var(--border)' }}>
          {!isCollapsed && (
            <div className="flex items-center space-x-3">
              <div className="w-9 h-9 rounded-xl flex items-center justify-center shadow-lg" style={{ background: 'linear-gradient(135deg, #6366f1, #8b5cf6)', boxShadow: '0 4px 14px 0 rgba(99,102,241,0.39)' }}>
                <PawPrint className="w-5 h-5 text-white" />
              </div>
              <div className="flex flex-col">
                <span className="font-extrabold text-lg tracking-tight" style={{ 
                  background: 'linear-gradient(135deg, #ffffff 30%, #a1a1aa)',
                  WebkitBackgroundClip: 'text',
                  WebkitTextFillColor: 'transparent',
                  backgroundClip: 'text'
                }}>Advoc AI</span>
              </div>
            </div>
          )}

          {isCollapsed && (
            <div className="w-9 h-9 rounded-xl flex items-center justify-center mx-auto shadow-lg" style={{ background: 'linear-gradient(135deg, #6366f1, #8b5cf6)', boxShadow: '0 4px 14px 0 rgba(99,102,241,0.39)' }}>
              <PawPrint className="w-5 h-5 text-white" />
            </div>
          )}

          {/* Desktop collapse button */}
          <button
            onClick={toggleCollapse}
            className="hidden md:flex p-1.5 rounded-md transition-all duration-200"
            style={{ 
              color: 'var(--text-muted)', 
              background: 'transparent', 
              border: 'none', 
              cursor: 'pointer' 
            }}
            onMouseOver={(e) => {
              e.currentTarget.style.color = 'var(--text-primary)';
              e.currentTarget.style.background = 'var(--bg-glass-hover)';
            }}
            onMouseOut={(e) => {
              e.currentTarget.style.color = 'var(--text-muted)';
              e.currentTarget.style.background = 'transparent';
            }}
            aria-label={isCollapsed ? "Expand sidebar" : "Collapse sidebar"}
          >
            {isCollapsed ? (
              <ChevronRight className="h-4 w-4" />
            ) : (
              <ChevronLeft className="h-4 w-4" />
            )}
          </button>
        </div>

        {/* Navigation */}
        <nav className="flex-1 px-3 py-4 overflow-y-auto">
          {sections.map(section => (
            <div key={section} className="mb-4">
              {!isCollapsed && (
                <div className="px-2 mb-2 text-xs font-semibold uppercase tracking-wider" style={{ color: 'var(--text-muted)' }}>
                  {section}
                </div>
              )}
              <ul className="space-y-1">
                {navigationItems.filter(item => item.section === section).map((item) => {
                  const Icon = item.icon;
                  const isActive = activeItem === item.id;

                  return (
                    <li key={item.id}>
                      <button
                        onClick={() => handleItemClick(item.id)}
                        className={`
                          w-full flex items-center space-x-2.5 px-3 py-2.5 rounded-md text-left transition-all duration-200 group relative
                          ${isActive ? "font-medium" : "font-normal"}
                          ${isCollapsed ? "justify-center px-2" : ""}
                        `}
                        style={{
                          background: isActive ? 'linear-gradient(135deg, rgba(99,102,241,0.15), rgba(139,92,246,0.05))' : 'transparent',
                          color: isActive ? '#818cf8' : 'var(--text-secondary)',
                          border: isActive ? '1px solid rgba(99,102,241,0.25)' : '1px solid transparent',
                          borderLeft: isActive ? '3px solid #6366f1' : '3px solid transparent',
                          cursor: 'pointer',
                        }}
                        onMouseOver={(e) => {
                          if (!isActive) {
                            e.currentTarget.style.background = 'var(--bg-glass-hover)';
                            e.currentTarget.style.color = 'var(--text-primary)';
                          }
                        }}
                        onMouseOut={(e) => {
                          if (!isActive) {
                            e.currentTarget.style.background = 'transparent';
                            e.currentTarget.style.color = 'var(--text-secondary)';
                          }
                        }}
                        title={isCollapsed ? item.name : undefined}
                      >
                        <div className="flex items-center justify-center min-w-[20px]">
                          <Icon className="h-4.5 w-4.5 flex-shrink-0" />
                        </div>
                        
                        {!isCollapsed && (
                          <div className="flex items-center justify-between w-full">
                            <span className="text-sm">{item.name}</span>
                          </div>
                        )}

                        {/* Tooltip for collapsed state */}
                        {isCollapsed && (
                          <div className="absolute left-full ml-2 px-2 py-1 text-xs rounded opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all duration-200 whitespace-nowrap z-50 shadow-md" style={{ background: 'var(--bg-card)', color: 'var(--text-primary)', border: '1px solid var(--border)' }}>
                            {item.name}
                          </div>
                        )}
                      </button>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </nav>
      </div>

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col w-full h-screen relative overflow-hidden">
        <main className="flex-1 p-6 md:p-8 pt-16 md:pt-8 w-full h-full flex flex-col">
          {children}
        </main>
      </div>
    </div>
  );
}
