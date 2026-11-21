"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, Eye, EyeOff, Lock, ShieldCheck, User } from "lucide-react";
import {
  API_BASE_URL,
  adminFetch,
  clearToken,
  getToken,
  saveToken,
} from "./lib";

export default function AdminLogin() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Already logged in? Ask the server whether the saved token is still valid.
  useEffect(() => {
    if (!getToken()) return;

    adminFetch("/admin/me")
      .then((res) => {
        if (res.ok) router.replace("/admin/dashboard");
        else clearToken();
      })
      .catch(() => {
        /* backend unreachable - stay on the login form */
      });
  }, [router]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);

    try {
      const res = await fetch(`${API_BASE_URL}/admin/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: username.trim(), password }),
      });

      const data = await res.json().catch(() => null);

      if (res.ok && data?.success && data.token) {
        saveToken(data.token);
        router.push("/admin/dashboard");
        return;
      }

      setError(
        data?.error ||
          (res.status === 503
            ? "Admin login is not set up on the server yet."
            : "Login failed. Please try again.")
      );
    } catch {
      setError("Could not reach the CivicLens server. Check your connection.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <main className="relative flex min-h-dvh items-center justify-center overflow-hidden bg-[#050816] px-4 text-slate-100">
      <div className="absolute left-[-10%] top-[-15%] h-[480px] w-[480px] rounded-full bg-fuchsia-500/10 blur-[130px]" />
      <div className="absolute bottom-[-20%] right-[-10%] h-[480px] w-[480px] rounded-full bg-violet-600/10 blur-[130px]" />

      <div className="relative w-full max-w-sm">
        <Link
          href="/"
          className="mb-6 inline-flex items-center gap-2 text-xs text-slate-500 transition hover:text-slate-300"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          Back to CivicLens
        </Link>

        <div className="glass-panel p-7">
          <div className="mb-6 flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-xl border border-fuchsia-400/30 bg-fuchsia-400/10 text-fuchsia-300">
              <ShieldCheck className="h-5 w-5" />
            </div>
            <div>
              <h1 className="text-lg font-bold">
                Civic<span className="text-fuchsia-300">Lens</span> Admin
              </h1>
              <p className="text-xs text-slate-500">
                Sign in to manage civic reports
              </p>
            </div>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            <label className="block">
              <span className="mb-1.5 block text-xs text-slate-400">
                Username
              </span>
              <div className="flex items-center gap-2 rounded-xl border border-white/10 bg-white/[0.03] px-3 focus-within:border-fuchsia-400/50">
                <User className="h-4 w-4 text-slate-500" />
                <input
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  autoComplete="username"
                  autoFocus
                  required
                  className="w-full bg-transparent py-3 text-sm outline-none"
                />
              </div>
            </label>

            <label className="block">
              <span className="mb-1.5 block text-xs text-slate-400">
                Password
              </span>
              <div className="flex items-center gap-2 rounded-xl border border-white/10 bg-white/[0.03] px-3 focus-within:border-fuchsia-400/50">
                <Lock className="h-4 w-4 text-slate-500" />
                <input
                  type={showPassword ? "text" : "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete="current-password"
                  required
                  className="w-full bg-transparent py-3 text-sm outline-none"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((v) => !v)}
                  className="text-slate-500 transition hover:text-slate-300"
                  aria-label={showPassword ? "Hide password" : "Show password"}
                >
                  {showPassword ? (
                    <EyeOff className="h-4 w-4" />
                  ) : (
                    <Eye className="h-4 w-4" />
                  )}
                </button>
              </div>
            </label>

            {error && (
              <div
                role="alert"
                className="rounded-xl border border-red-400/20 bg-red-400/5 px-3 py-2.5 text-xs text-red-300"
              >
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={submitting || !username || !password}
              className="w-full rounded-xl bg-gradient-to-r from-fuchsia-500 via-violet-500 to-amber-400 px-5 py-3.5 text-sm font-semibold text-black transition hover:scale-[1.01] disabled:cursor-not-allowed disabled:opacity-40"
            >
              {submitting ? "Signing in..." : "Sign in"}
            </button>
          </form>
        </div>

        <p className="mt-5 text-center text-[11px] text-slate-600">
          Access is verified by the CivicLens server.
        </p>
      </div>
    </main>
  );
}
