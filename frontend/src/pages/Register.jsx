import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { IndianRupee } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { fmtErr } from "@/lib/api";

export default function Register() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({ name: "", email: "", password: "", role: "owner" });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await register(form);
      navigate("/");
    } catch (err) {
      setError(fmtErr(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#F8FAFC] p-6">
      <div className="w-full max-w-md animate-fade-up">
        <div className="flex items-center gap-2.5 mb-10">
          <div className="w-10 h-10 rounded-xl bg-[#5E35B1] flex items-center justify-center shadow-[0_6px_18px_rgba(94,53,177,0.4)]">
            <IndianRupee className="w-5 h-5 text-white" />
          </div>
          <span className="font-heading font-bold text-2xl text-slate-900">bill4pe</span>
        </div>
        <h1 className="font-heading text-3xl sm:text-4xl font-bold text-slate-900 tracking-tight">
          Create your account
        </h1>
        <p className="text-slate-500 mt-2 mb-8 text-sm sm:text-base">
          Start invoicing and collecting via UPI in minutes.
        </p>
        <form onSubmit={submit} className="space-y-5" data-testid="register-form">
          {error && (
            <div data-testid="register-error-alert" className="px-4 py-3 rounded-lg bg-rose-50 border border-rose-200 text-rose-700 text-sm">
              {error}
            </div>
          )}
          <div>
            <label className="field-label" htmlFor="reg-name">Full name</label>
            <input id="reg-name" data-testid="auth-signup-name-input" required className="field-input" placeholder="Asha Sharma" value={form.name} onChange={set("name")} />
          </div>
          <div>
            <label className="field-label" htmlFor="reg-email">Email</label>
            <input id="reg-email" data-testid="auth-signup-email-input" type="email" required autoComplete="email" className="field-input" placeholder="you@business.in" value={form.email} onChange={set("email")} />
          </div>
          <div>
            <label className="field-label" htmlFor="reg-password">Password</label>
            <input id="reg-password" data-testid="auth-signup-password-input" type="password" required minLength={6} autoComplete="new-password" className="field-input" placeholder="Min. 6 characters" value={form.password} onChange={set("password")} />
          </div>
          <div>
            <label className="field-label" htmlFor="reg-role">Role</label>
            <select id="reg-role" data-testid="auth-signup-role-select" className="field-input" value={form.role} onChange={set("role")}>
              <option value="owner">Business Owner / Admin</option>
              <option value="staff">Team Member / Billing Staff</option>
            </select>
          </div>
          <button
            data-testid="auth-signup-submit-button"
            type="submit"
            disabled={loading}
            className="w-full h-11 rounded-lg bg-[#5E35B1] hover:bg-[#512DA8] text-white font-semibold text-sm transition-all shadow-[0_6px_18px_rgba(94,53,177,0.35)] focus:outline-none focus:ring-2 focus:ring-[#5E35B1]/50 focus:ring-offset-2 disabled:opacity-60"
          >
            {loading ? "Creating account…" : "Create account"}
          </button>
        </form>
        <p className="text-sm text-slate-500 mt-6">
          Already have an account?{" "}
          <Link data-testid="register-login-link" to="/login" className="text-[#5E35B1] font-semibold hover:underline">
            Sign in
          </Link>
        </p>
      </div>
    </div>
  );
}
