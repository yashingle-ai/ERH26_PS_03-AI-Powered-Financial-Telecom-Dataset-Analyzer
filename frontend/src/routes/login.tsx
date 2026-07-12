import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ArrowRight, ShieldCheck } from "lucide-react";
import { useState, type FormEvent } from "react";
import { api, ApiError } from "@/lib/api";
import { setSession } from "@/lib/auth";

export const Route = createFileRoute("/login")({
  head: () => ({
    meta: [
      { title: "Sign in — ERakshak" },
      { name: "description", content: "Analyst sign-in for the ERakshak forensic intelligence platform." },
    ],
  }),
  component: LoginPage,
});

function LoginPage() {
  const nav = useNavigate();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    const fd = new FormData(e.currentTarget);
    const username = String(fd.get("username") || "").trim();
    const password = String(fd.get("password") || "");
    try {
      const token = await api.login(username, password);
      setSession(token.access_token, username);
      await nav({ to: "/investigations" });
    } catch (err) {
      const msg = err instanceof ApiError
        ? err.message
        : "Cannot reach API. Start backend on :8000.";
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="relative min-h-screen overflow-hidden">
      <div className="absolute inset-0 grid-bg opacity-40" aria-hidden />
      <div className="absolute inset-0 pointer-events-none" aria-hidden>
        <svg className="h-full w-full" preserveAspectRatio="none" viewBox="0 0 1440 900">
          <defs>
            <radialGradient id="glow" cx="20%" cy="30%" r="60%">
              <stop offset="0%" stopColor="#1AA6A6" stopOpacity="0.35" />
              <stop offset="100%" stopColor="#0B1F33" stopOpacity="0" />
            </radialGradient>
            <linearGradient id="edge" x1="0" x2="1">
              <stop offset="0%" stopColor="#1AA6A6" stopOpacity="0" />
              <stop offset="50%" stopColor="#1AA6A6" stopOpacity="0.6" />
              <stop offset="100%" stopColor="#1AA6A6" stopOpacity="0" />
            </linearGradient>
          </defs>
          <rect width="1440" height="900" fill="url(#glow)" />
          {[220, 360, 500, 640, 780].map((y, i) => (
            <line key={i} x1="0" x2="1440" y1={y} y2={y} stroke="#1AA6A6" strokeOpacity="0.08" strokeDasharray="2 6" />
          ))}
        </svg>
      </div>

      <div className="relative z-10 mx-auto grid min-h-screen max-w-7xl grid-cols-1 items-center gap-16 px-6 py-10 lg:grid-cols-[1.15fr_1fr]">
        <div className="animate-fade-up">
          <div className="mb-6 inline-flex items-center gap-2 rounded border border-primary/30 bg-primary/10 px-2.5 py-1 text-mono text-[10px] uppercase tracking-[0.25em] text-primary">
            <ShieldCheck className="h-3 w-3" />
            Restricted · Analyst access
          </div>
          <h1 className="font-display text-5xl font-semibold leading-[1.05] tracking-tight text-foreground md:text-7xl">
            ERakshak<span className="text-primary">.</span>
          </h1>
          <p className="mt-5 max-w-xl text-lg text-muted-foreground md:text-xl">
            Fuse <span className="text-foreground">bank</span>,{" "}
            <span className="text-foreground">call</span>, and{" "}
            <span className="text-foreground">IP</span> evidence into one investigation.
          </p>
        </div>

        <div className="glass w-full max-w-md justify-self-center rounded-lg p-7 shadow-2xl lg:justify-self-end">
          <div className="mb-6">
            <div className="text-mono text-[10px] uppercase tracking-[0.3em] text-primary">Sign in</div>
            <h2 className="mt-1 text-xl font-semibold">Analyst access</h2>
            <p className="mt-1 text-xs text-muted-foreground">
              Use API credentials (`admin` / `analyst`). Backend must be running.
            </p>
          </div>

          <form onSubmit={submit} className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="username" className="text-mono text-[11px] uppercase tracking-wider">
                Username
              </Label>
              <Input
                id="username"
                name="username"
                required
                defaultValue="admin"
                className="text-mono bg-surface"
                autoComplete="username"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="password" className="text-mono text-[11px] uppercase tracking-wider">
                Password
              </Label>
              <Input
                id="password"
                name="password"
                type="password"
                required
                defaultValue="adminpass"
                className="text-mono bg-surface"
                autoComplete="current-password"
              />
            </div>

            {error && (
              <p className="rounded border border-[color:var(--risk-high)]/40 bg-[color:var(--risk-high)]/10 px-3 py-2 text-[12px] text-[color:var(--risk-high)]">
                {error}
              </p>
            )}

            <Button type="submit" disabled={loading} className="mt-2 w-full bg-primary text-primary-foreground hover:opacity-90">
              {loading ? "Verifying…" : "Sign in"}
              <ArrowRight className="ml-2 h-4 w-4" />
            </Button>
          </form>
        </div>
      </div>

      <div className="text-mono absolute bottom-4 left-6 z-10 text-[10px] uppercase tracking-[0.25em] text-muted-foreground">
        ERakshak · Forensic Intelligence Platform
      </div>
      <Link
        to="/login"
        className="text-mono absolute bottom-4 right-6 z-10 text-[10px] uppercase tracking-[0.25em] text-muted-foreground hover:text-primary"
      >
        API · {import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000"}
      </Link>
    </div>
  );
}
