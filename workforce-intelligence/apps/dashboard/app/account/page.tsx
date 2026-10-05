"use client";

import { useState, type FormEvent } from "react";

import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Protected } from "@/components/Protected";
import { Loading } from "@/components/ui";

const MIN_PASSWORD_LENGTH = 10;

function AccountInner() {
  const { me } = useAuth();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [ok, setOk] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  if (!me) return <Loading label="Loading your profile…" />;

  async function submit(e: FormEvent) {
    e.preventDefault();
    setOk(null);
    setErr(null);
    if (next.length < MIN_PASSWORD_LENGTH) {
      setErr(`The new password must be at least ${MIN_PASSWORD_LENGTH} characters.`);
      return;
    }
    if (next !== confirm) {
      setErr("The new passwords do not match.");
      return;
    }
    setBusy(true);
    try {
      await api.changePassword({ current_password: current, new_password: next });
      setOk("Password changed. Use the new password next time you sign in.");
      setCurrent("");
      setNext("");
      setConfirm("");
    } catch (e2) {
      if (e2 instanceof ApiError && e2.status === 401) return;
      setErr(e2 instanceof Error ? e2.message : "Failed to change password.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <h1 className="page-title">Account</h1>
      <p className="page-sub">
        {me.email} · {me.role}
        {me.organization_id ? ` · org ${me.organization_id}` : " · platform level"}
      </p>

      <div className="card" style={{ maxWidth: 520 }}>
        <h2>Change password</h2>
        <form onSubmit={submit}>
          <div className="field">
            <label htmlFor="current-password">Current password</label>
            <input
              id="current-password"
              type="password"
              autoComplete="current-password"
              value={current}
              onChange={(e) => setCurrent(e.target.value)}
              required
            />
          </div>
          <div className="field">
            <label htmlFor="new-password">New password (at least {MIN_PASSWORD_LENGTH} characters)</label>
            <input
              id="new-password"
              type="password"
              autoComplete="new-password"
              value={next}
              onChange={(e) => setNext(e.target.value)}
              required
            />
          </div>
          <div className="field">
            <label htmlFor="confirm-password">Repeat new password</label>
            <input
              id="confirm-password"
              type="password"
              autoComplete="new-password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              required
            />
          </div>
          <button className="primary" type="submit" disabled={busy}>
            {busy ? "Saving…" : "Change password"}
          </button>
        </form>
        {err ? (
          <div className="notice error" style={{ marginTop: 12 }}>
            {err}
          </div>
        ) : null}
        {ok ? (
          <div
            className="notice"
            style={{
              marginTop: 12,
              color: "var(--green)",
              borderColor: "rgba(63, 182, 127, 0.4)",
              background: "rgba(63, 182, 127, 0.08)",
            }}
          >
            {ok}
          </div>
        ) : null}
      </div>
    </>
  );
}

export default function AccountPage() {
  return (
    <Protected>
      <AccountInner />
    </Protected>
  );
}
