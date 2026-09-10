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
    <header className="app-topbar sticky top-0 z-30 backdrop-blur-xl bg-white/85 border-b border-soft">
      <div className="max-w-screen-sm mx-auto px-4 h-14 min-h-[56px] flex items-center justify-between">
        {showBack ? (
          <button
            onClick={() => navigate(-1)}
            data-testid="topbar-back-btn"
            className="press-down -ml-2 w-11 h-11 grid place-items-center rounded-full hover:bg-gray-100 touch-target"
          >
            <ChevronLeft className="w-5 h-5 text-navy" strokeWidth={2.2} />
          </button>
        ) : (
          <div className="inline-flex items-center gap-2" data-testid="appshell-logo">
            <img src="/logo.png?v=7" alt="Bil4Pe — The Intelligent Billing" className="h-10 sm:h-12 w-auto max-w-[112px] sm:max-w-none rounded-md object-contain" />
            {isCorporate && (
              <span
                data-testid="appshell-corporate-chip"
                title={user?.corporate_name || 'Corporate'}
                className="inline-flex items-center gap-1 bg-navy text-white text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full"
              >
                <Building2 className="w-3 h-3" />
                <span className="max-w-[64px] sm:max-w-[100px] truncate">{user?.corporate_name || 'Corporate'}</span>
              </span>
            )}
          </div>
        )}
        <button
          onClick={() => navigate('/app/profile')}
          data-testid="topbar-profile-btn"
          className="press-down w-11 h-11 rounded-full bg-navy text-white grid place-items-center font-display font-bold text-sm hover:bg-[#0F1631] touch-target"
          title="Profile"
        >
          <User className="w-4 h-4" />
        </button>
      </div>
    </header>
  );
};

const BottomNav = () => {
  const { user } = useAuth();
  const isAdmin = user?.role === 'admin' && user?.company_id;
  const link = ({ isActive }) =>
    `min-w-0 flex-1 flex flex-col items-center justify-center gap-1 py-2.5 px-1 text-[10px] sm:text-xs ${
      isActive ? 'text-navy font-semibold' : 'text-slate-400'
    }`;
  return (
    <nav className="app-bottom-nav sticky bottom-0 z-30 bg-white border-t border-soft">
      <div className="max-w-screen-sm mx-auto flex">
        <NavLink to="/app" end className={link} data-testid="bottomnav-home">
          <Home className="w-5 h-5" />
          <span className="bottom-nav-label truncate max-w-full">Home</span>
        </NavLink>
        {isAdmin && (
          <NavLink to="/app/company" className={link} data-testid="bottomnav-company">
            <Building2 className="w-5 h-5" />
            <span className="bottom-nav-label truncate max-w-full">Company</span>
          </NavLink>
        )}
        <NavLink to="/app/dashboard" className={link} data-testid="bottomnav-dashboard">
          <LayoutDashboard className="w-5 h-5" />
          <span className="bottom-nav-label truncate max-w-full">Dashboard</span>
        </NavLink>
        <NavLink to="/app/reports" className={link} data-testid="bottomnav-reports">
          <FileBarChart className="w-5 h-5" />
          <span className="bottom-nav-label truncate max-w-full">Reports</span>
        </NavLink>
        <NavLink to="/app/wallet" className={link} data-testid="bottomnav-wallet">
          <Wallet className="w-5 h-5" />
          <span className="bottom-nav-label truncate max-w-full">Wallet</span>
        </NavLink>
      </div>
    </nav>
  );
};

export default function AppShell() {
  return (
    <div className="app-shell min-h-screen min-h-[100dvh] flex flex-col bg-white">
      <TopBar />
      <main className="app-main flex-1 max-w-screen-sm w-full mx-auto px-4 py-4 pb-6">
        <Outlet />
      </main>
      <BottomNav />
      <PWAInstallBanner />
      <OnboardingTour />
    </div>
  );
}
