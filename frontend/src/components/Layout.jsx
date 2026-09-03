import { useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { LayoutDashboard, FileText, Users, Settings, LogOut, Menu, X, IndianRupee } from "lucide-react";
import { useAuth } from "@/context/AuthContext";

const NAV = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true, testid: "nav-dashboard" },
  { to: "/invoices", label: "Invoices", icon: FileText, testid: "nav-invoices" },
  { to: "/customers", label: "Customers", icon: Users, testid: "nav-customers" },
  { to: "/settings", label: "Settings", icon: Settings, testid: "nav-settings" },
];

function SidebarContent({ onNavigate }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const doLogout = async () => {
    await logout();
    navigate("/login");
  };
  return (
    <div className="flex flex-col h-full bg-[#0F172A] text-slate-300">
      <div className="px-6 pt-7 pb-6">
        <div className="flex items-center gap-2.5">
          <div className="w-9 h-9 rounded-lg bg-[#5E35B1] flex items-center justify-center">
            <IndianRupee className="w-5 h-5 text-white" />
          </div>
          <div>
            <div className="font-heading font-bold text-white text-lg leading-none">bill4pe</div>
            <div className="text-[10px] tracking-[0.22em] uppercase text-slate-500 mt-1">UPI-first billing</div>
          </div>
        </div>
      </div>
      <nav className="flex-1 px-3 space-y-1">
        {NAV.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            data-testid={item.testid}
            onClick={onNavigate}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3.5 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                isActive
                  ? "bg-[#5E35B1] text-white shadow-[0_4px_14px_rgba(94,53,177,0.45)]"
                  : "hover:bg-[#1E293B] hover:text-white"
              }`
            }
          >
            <item.icon className="w-4.5 h-4.5 w-[18px] h-[18px]" />
            {item.label}
          </NavLink>
        ))}
      </nav>
      <div className="p-4 border-t border-slate-800">
        <div className="flex items-center gap-3 px-2">
          <div className="w-9 h-9 rounded-full bg-[#1E293B] border border-slate-700 flex items-center justify-center text-sm font-bold text-white uppercase">
            {(user?.name || "U")[0]}
          </div>
          <div className="min-w-0 flex-1">
            <div className="text-sm font-semibold text-white truncate">{user?.name}</div>
            <div className="text-xs text-slate-500 truncate">{user?.email}</div>
          </div>
          <button
            data-testid="nav-logout-button"
            onClick={doLogout}
            title="Log out"
            className="p-2 rounded-lg text-slate-400 hover:text-white hover:bg-[#1E293B] transition-colors"
          >
            <LogOut className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  );
}

export default function Layout() {
  const [open, setOpen] = useState(false);
  return (
    <div className="min-h-screen bg-[#F8FAFC]">
      <aside className="hidden lg:block fixed inset-y-0 left-0 w-64 z-30 print-hidden">
        <SidebarContent />
      </aside>

      <div className="lg:hidden sticky top-0 z-40 bg-[#0F172A] text-white flex items-center justify-between px-4 h-14 print-hidden">
        <div className="flex items-center gap-2 font-heading font-bold">
          <div className="w-7 h-7 rounded-md bg-[#5E35B1] flex items-center justify-center">
            <IndianRupee className="w-4 h-4" />
          </div>
          bill4pe
        </div>
        <button data-testid="nav-mobile-menu-button" onClick={() => setOpen(true)} className="p-2">
          <Menu className="w-5 h-5" />
        </button>
      </div>

      {open && (
        <div className="lg:hidden fixed inset-0 z-50 print-hidden">
          <div className="absolute inset-0 bg-slate-900/60" onClick={() => setOpen(false)} />
          <div className="absolute inset-y-0 left-0 w-72 animate-fade-up">
            <button
              data-testid="nav-mobile-close-button"
              onClick={() => setOpen(false)}
              className="absolute top-4 right-4 z-10 p-2 text-slate-400 hover:text-white"
            >
              <X className="w-5 h-5" />
            </button>
            <SidebarContent onNavigate={() => setOpen(false)} />
          </div>
        </div>
      )}

      <main className="lg:pl-64">
        <div className="p-4 sm:p-6 lg:p-8 max-w-7xl mx-auto">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
