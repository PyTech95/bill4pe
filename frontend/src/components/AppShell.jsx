import React from 'react';
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { Home, LayoutDashboard, Wallet, User, FileBarChart, ChevronLeft, Building2 } from 'lucide-react';
import OnboardingTour from '@/components/OnboardingTour';
import PWAInstallBanner from '@/components/PWAInstallBanner';
import { useAuth } from '@/lib/auth';

const TopBar = () => {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const { user } = useAuth();
  const showBack = pathname !== '/app';
  const isCorporate = user?.user_type === 'corporate';

  return (
    <header className="sticky top-0 z-30 backdrop-blur-xl bg-white/85 border-b border-soft">
      <div className="max-w-screen-sm mx-auto px-4 h-14 flex items-center justify-between">
        {showBack ? (
          <button
            onClick={() => navigate(-1)}
            data-testid="topbar-back-btn"
            className="press-down -ml-2 p-2 rounded-full hover:bg-gray-100"
          >
            <ChevronLeft className="w-5 h-5 text-navy" strokeWidth={2.2} />
          </button>
        ) : (
          <div className="inline-flex items-center gap-2" data-testid="appshell-logo">
            <img src="/logo.png" alt="Bill4Pe — The Intelligent Building" className="h-12 w-auto rounded-md object-contain" />
            {isCorporate && (
              <span
                data-testid="appshell-corporate-chip"
                title={user?.corporate_name || 'Corporate'}
                className="inline-flex items-center gap-1 bg-navy text-brand text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full"
              >
                <Building2 className="w-3 h-3" />
                <span className="max-w-[100px] truncate">{user?.corporate_name || 'Corporate'}</span>
              </span>
            )}
          </div>
        )}
        <button
          onClick={() => navigate('/app/profile')}
          data-testid="topbar-profile-btn"
          className="press-down w-9 h-9 rounded-full bg-navy text-brand grid place-items-center font-display font-bold text-sm hover:bg-[#0F1631]"
          title="Profile"
        >
          <User className="w-4 h-4" />
        </button>
      </div>
    </header>
  );
};

const BottomNav = () => {
  const link = ({ isActive }) =>
    `flex-1 flex flex-col items-center justify-center gap-1 py-2 text-xs ${
      isActive ? 'text-navy font-semibold' : 'text-slate-400'
    }`;
  return (
    <nav className="sticky bottom-0 z-30 bg-white border-t border-soft">
      <div className="max-w-screen-sm mx-auto flex">
        <NavLink to="/app" end className={link} data-testid="bottomnav-home">
          <Home className="w-5 h-5" />
          <span>Home</span>
        </NavLink>
        <NavLink to="/app/dashboard" className={link} data-testid="bottomnav-dashboard">
          <LayoutDashboard className="w-5 h-5" />
          <span>Dashboard</span>
        </NavLink>
        <NavLink to="/app/reports" className={link} data-testid="bottomnav-reports">
          <FileBarChart className="w-5 h-5" />
          <span>Reports</span>
        </NavLink>
        <NavLink to="/app/wallet" className={link} data-testid="bottomnav-wallet">
          <Wallet className="w-5 h-5" />
          <span>Wallet</span>
        </NavLink>
      </div>
    </nav>
  );
};

export default function AppShell() {
  return (
    <div className="min-h-screen flex flex-col bg-white">
      <TopBar />
      <main className="flex-1 max-w-screen-sm w-full mx-auto px-4 py-4 pb-6">
        <Outlet />
      </main>
      <BottomNav />
      <PWAInstallBanner />
      <OnboardingTour />
    </div>
  );
}
