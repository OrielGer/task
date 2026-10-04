"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";

import { useAuth } from "@/lib/auth";
import { ApiError } from "@/lib/api";

const DEMO_LOGINS = [
  { label: "Admin", email: "admin@acme.example", password: "Passw0rd!admin" },
  { label: "Manager", email: "manager@acme.example", password: "Passw0rd!mgr" },
  { label: "Employee", email: "daniel@acme.example", password: "Passw0rd!emp" },
];

export default function LoginPage() {
  const router = useRouter();
  const { token, ready, login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // Already signed in → go home.
  useEffect(() => {
    if (ready && token) router.replace("/");
  }, [ready, token, router]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login({ email: email.trim(), password });
      router.replace("/");
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setError("Invalid email or password.");
      } else if (err instanceof ApiError && err.status === 0) {
        setError("Could not reach the API. Is the backend running?");
      } else {
        setError(err instanceof Error ? err.message : "Login failed.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  function fill(demo: (typeof DEMO_LOGINS)[number]) {
    setEmail(demo.email);
    setPassword(demo.password);
    setError(null);
  }

  return (
    <div className="login-wrap">
      <div className="card login-card">
        <h1 className="page-title" style={{ marginBottom: 6 }}>
          Sign in
        </h1>
        <p className="page-sub" style={{ marginBottom: 20 }}>
          Workforce Intelligence dashboard
        </p>

        <form onSubmit={onSubmit}>
          <div className="field">
            <label htmlFor="email">Email</label>
            <input
              id="email"
              type="email"
              autoComplete="username"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </div>
          <div className="field">
            <label htmlFor="password">Password</label>
            <input
              id="password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </div>

          {error ? (
            <div className="notice error" style={{ marginBottom: 14 }}>
              {error}
            </div>
          ) : null}

          <button className="primary" type="submit" disabled={submitting} style={{ width: "100%" }}>
            {submitting ? "Signing in…" : "Sign in"}
          </button>
        </form>

        <div className="demo-logins">
          <div style={{ marginBottom: 6 }}>Demo accounts (click to fill):</div>
          <div className="row">
            {DEMO_LOGINS.map((d) => (
              <button key={d.email} type="button" className="small-btn" onClick={() => fill(d)}>
                {d.label}
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
