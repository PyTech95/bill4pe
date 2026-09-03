import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { IndianRupee } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { fmtErr } from "@/lib/api";

const HERO =
  "https://images.unsplash.com/photo-1515378791036-0648a3ef77b2?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NjA1NzV8MHwxfHNlYXJjaHwxfHxvZmZpY2UlMjBwcm9mZXNzaW9uYWwlMjB3b3JraW5nJTIwbGFwdG9wfGVufDB8fHx8MTc4NzYwOTkyMnww&ixlib=rb-4.1.0&q=85";

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await login(email, password);
      navigate("/");
    } catch (err) {
      setError(fmtErr(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex bg-[#F8FAFC]">
      <div className="flex-1 flex items-center justify-center p-6 sm:p-10">
        <div className="w-full max-w-md animate-fade-up">
          <div className="flex items-center gap-2.5 mb-10">
            <div className="w-10 h-10 rounded-xl bg-[#5E35B1] flex items-center justify-center shadow-[0_6px_18px_rgba(94,53,177,0.4)]">
              <IndianRupee className="w-5 h-5 text-white" />
            </div>
            <span className="font-heading font-bold text-2xl text-slate-900">bill4pe</span>
          </div>
          <h1 className="font-heading text-3xl sm:text-4xl font-bold text-slate-900 tracking-tight">
            Welcome back
          </h1>
          <p className="text-slate-500 mt-2 mb-8 text-sm sm:text-base">
            Sign in to manage invoices, customers and UPI collections.
          </p>
          <form onSubmit={submit} className="space-y-5" data-testid="login-form">
            {error && (
              <div data-testid="login-error-alert" className="px-4 py-3 rounded-lg bg-rose-50 border border-rose-200 text-rose-700 text-sm">
                {error}
              </div>
            )}
            <div>
              <label className="field-label" htmlFor="login-email">Email</label>
              <input
                id="login-email"
                data-testid="auth-login-email-input"
                type="email"
                required
                autoComplete="email"
                className="field-input"
                placeholder="you@business.in"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </div>
            <div>
              <label className="field-label" htmlFor="login-password">Password</label>
              <input
                id="login-password"
                data-testid="auth-login-password-input"
                type="password"
                required
                autoComplete="current-password"
                className="field-input"
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </div>
            <button
              data-testid="auth-login-submit-button"
              type="submit"
              disabled={loading}
              className="w-full h-11 rounded-lg bg-[#5E35B1] hover:bg-[#512DA8] text-white font-semibold text-sm transition-all shadow-[0_6px_18px_rgba(94,53,177,0.35)] hover:shadow-[0_8px_24px_rgba(94,53,177,0.45)] focus:outline-none focus:ring-2 focus:ring-[#5E35B1]/50 focus:ring-offset-2 disabled:opacity-60"
            >
              {loading ? "Signing in…" : "Sign in"}
            </button>
          </form>
          <p className="text-sm text-slate-500 mt-6">
            New to bill4pe?{" "}
            <Link data-testid="login-signup-link" to="/register" className="text-[#5E35B1] font-semibold hover:underline">
              Create an account
            </Link>
          </p>
        </div>
      </div>
      <div className="hidden lg:block w-[46%] relative">
        <img src={HERO} alt="Workspace" className="absolute inset-0 w-full h-full object-cover" />
        <div className="absolute inset-0 bg-gradient-to-t from-[#0F172A] via-[#0F172A]/60 to-transparent" />
        <div className="absolute bottom-0 p-12">
          <p className="font-heading text-3xl font-bold text-white leading-snug">
            Bills that get paid<br />at UPI speed.
          </p>
          <p className="text-slate-300 mt-3 text-sm max-w-sm">
            GST-ready invoices, instant UPI payment links and QR codes, and clean books for your business.
          </p>
        </div>
      </div>
    </div>
  );
}
