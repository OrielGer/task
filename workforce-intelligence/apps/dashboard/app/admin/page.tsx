"use client";

import { useState, type FormEvent, type ReactNode } from "react";

import { api, ApiError } from "@/lib/api";
import { isAdminRole, useAuth } from "@/lib/auth";
import { Protected } from "@/components/Protected";
import { ErrorNotice, Loading } from "@/components/ui";
import type {
  DeviceEnrollment,
  OrganizationSummary,
  ProvisionableRole,
} from "@/lib/types";

/** Normalize an API error into a human-readable message. */
function message(err: unknown, fallback: string): string {
  if (err instanceof ApiError) return err.message;
  if (err instanceof Error) return err.message;
  return fallback;
}

/** Inline success / error line shared by every form. */
function FormStatus({ ok, err }: { ok: string | null; err: string | null }) {
  if (err) {
    return (
      <div className="notice error" style={{ marginTop: 12 }}>
        {err}
      </div>
    );
  }
  if (ok) {
    return (
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
    );
  }
  return null;
}

function Card({ title, sub, children }: { title: string; sub?: string; children: ReactNode }) {
  return (
    <div className="card">
      <h2>{title}</h2>
      {sub ? (
        <p className="muted small" style={{ marginTop: -6, marginBottom: 14 }}>
          {sub}
        </p>
      ) : null}
      {children}
    </div>
  );
}

/** Copy-to-clipboard button with transient confirmation. */
function CopyButton({ value }: { value: string }) {
  const [copied, setCopied] = useState(false);
  async function copy() {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard unavailable — user can select manually */
    }
  }
  return (
    <button type="button" className="small-btn" onClick={copy}>
      {copied ? "Copied" : "Copy"}
    </button>
  );
}

// ── Create organization (SUPER_ADMIN only) ───────────────────────────────────
function CreateOrgForm({ onCreated }: { onCreated: (org: OrganizationSummary) => void }) {
  const [name, setName] = useState("");
  const [domains, setDomains] = useState("");
  const [busy, setBusy] = useState(false);
  const [ok, setOk] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setOk(null);
    setErr(null);
    setBusy(true);
    try {
      const org = await api.createOrganization({
        name: name.trim(),
        allowlisted_domains: parseDomains(domains),
      });
      setOk(`Created organization "${org.name}" (${org.id}).`);
      setName("");
      setDomains("");
      onCreated(org);
    } catch (e2) {
      if (e2 instanceof ApiError && e2.status === 401) return;
      setErr(message(e2, "Failed to create organization."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card
      title="Create organization"
      sub="Super admins can provision a new tenant. The new org id is applied below automatically."
    >
      <form onSubmit={submit}>
        <div className="field">
          <label htmlFor="org-name">Name</label>
          <input
            id="org-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Acme Inc."
            required
          />
        </div>
        <div className="field">
          <label htmlFor="org-domains">Allowlisted domains (comma or newline separated)</label>
          <textarea
            id="org-domains"
            rows={2}
            value={domains}
            onChange={(e) => setDomains(e.target.value)}
            placeholder="docs.google.com, crm.acme.com"
          />
        </div>
        <button className="primary" type="submit" disabled={busy || !name.trim()}>
          {busy ? "Creating…" : "Create organization"}
        </button>
        <FormStatus ok={ok} err={err} />
      </form>
    </Card>
  );
}

// ── Create user ───────────────────────────────────────────────────────────────
function CreateUserForm({ orgId }: { orgId: string }) {
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<ProvisionableRole>("EMPLOYEE");
  const [busy, setBusy] = useState(false);
  const [ok, setOk] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setOk(null);
    setErr(null);
    if (!orgId) {
      setErr("Select an organization first.");
      return;
    }
    setBusy(true);
    try {
      const u = await api.createUser(orgId, {
        email: email.trim(),
        full_name: fullName.trim(),
        password,
        role,
      });
      setOk(`Created user ${u.email} (${u.role}).`);
      setEmail("");
      setFullName("");
      setPassword("");
      setRole("EMPLOYEE");
    } catch (e2) {
      if (e2 instanceof ApiError && e2.status === 401) return;
      setErr(message(e2, "Failed to create user."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card title="Create user" sub="Provision a login for a manager or employee.">
      <form onSubmit={submit}>
        <div className="row" style={{ marginBottom: 0 }}>
          <div className="field" style={{ flex: "1 1 220px" }}>
            <label htmlFor="user-email">Email</label>
            <input
              id="user-email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="person@acme.com"
              required
            />
          </div>
          <div className="field" style={{ flex: "1 1 220px" }}>
            <label htmlFor="user-name">Full name</label>
            <input
              id="user-name"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              placeholder="Jane Doe"
              required
            />
          </div>
        </div>
        <div className="row" style={{ marginBottom: 0 }}>
          <div className="field" style={{ flex: "1 1 220px" }}>
            <label htmlFor="user-pw">Password</label>
            <input
              id="user-pw"
              type="password"
              autoComplete="new-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </div>
          <div className="field" style={{ flex: "1 1 160px" }}>
            <label htmlFor="user-role">Role</label>
            <select
              id="user-role"
              value={role}
              onChange={(e) => setRole(e.target.value as ProvisionableRole)}
            >
              <option value="EMPLOYEE">EMPLOYEE</option>
              <option value="MANAGER">MANAGER</option>
              <option value="ORG_ADMIN">ORG_ADMIN</option>
            </select>
          </div>
        </div>
        <button className="primary" type="submit" disabled={busy}>
          {busy ? "Creating…" : "Create user"}
        </button>
        <FormStatus ok={ok} err={err} />
      </form>
    </Card>
  );
}

// ── Create employee ────────────────────────────────────────────────────────────
function CreateEmployeeForm({ orgId }: { orgId: string }) {
  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [userId, setUserId] = useState("");
  const [busy, setBusy] = useState(false);
  const [ok, setOk] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setOk(null);
    setErr(null);
    if (!orgId) {
      setErr("Select an organization first.");
      return;
    }
    setBusy(true);
    try {
      const emp = await api.createEmployee(orgId, {
        display_name: displayName.trim(),
        email: email.trim(),
        user_id: userId.trim() || undefined,
      });
      setOk(`Created employee ${emp.display_name} (${emp.id}).`);
      setDisplayName("");
      setEmail("");
      setUserId("");
    } catch (e2) {
      if (e2 instanceof ApiError && e2.status === 401) return;
      setErr(message(e2, "Failed to create employee."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card
      title="Create employee"
      sub="Register a monitored employee profile, optionally linked to an existing user."
    >
      <form onSubmit={submit}>
        <div className="row" style={{ marginBottom: 0 }}>
          <div className="field" style={{ flex: "1 1 220px" }}>
            <label htmlFor="emp-name">Display name</label>
            <input
              id="emp-name"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              placeholder="Jane Doe"
              required
            />
          </div>
          <div className="field" style={{ flex: "1 1 220px" }}>
            <label htmlFor="emp-email">Email</label>
            <input
              id="emp-email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="jane@acme.com"
              required
            />
          </div>
        </div>
        <div className="field">
          <label htmlFor="emp-user">Link to user id (optional)</label>
          <input
            id="emp-user"
            value={userId}
            onChange={(e) => setUserId(e.target.value)}
            placeholder="user id"
          />
        </div>
        <button className="primary" type="submit" disabled={busy}>
          {busy ? "Creating…" : "Create employee"}
        </button>
        <FormStatus ok={ok} err={err} />
      </form>
    </Card>
  );
}

// ── Create team ─────────────────────────────────────────────────────────────────
function CreateTeamForm({ orgId }: { orgId: string }) {
  const [name, setName] = useState("");
  const [managerUserId, setManagerUserId] = useState("");
  const [busy, setBusy] = useState(false);
  const [ok, setOk] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setOk(null);
    setErr(null);
    if (!orgId) {
      setErr("Select an organization first.");
      return;
    }
    setBusy(true);
    try {
      const team = await api.createTeam(orgId, name.trim(), managerUserId.trim() || undefined);
      setOk(`Created team "${team.name}" (${team.id}).`);
      setName("");
      setManagerUserId("");
    } catch (e2) {
      if (e2 instanceof ApiError && e2.status === 401) return;
      setErr(message(e2, "Failed to create team."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card title="Create team" sub="Group employees under a manager.">
      <form onSubmit={submit}>
        <div className="row" style={{ marginBottom: 0 }}>
          <div className="field" style={{ flex: "1 1 220px" }}>
            <label htmlFor="team-name">Name</label>
            <input
              id="team-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Sales"
              required
            />
          </div>
          <div className="field" style={{ flex: "1 1 220px" }}>
            <label htmlFor="team-mgr">Manager user id (optional)</label>
            <input
              id="team-mgr"
              value={managerUserId}
              onChange={(e) => setManagerUserId(e.target.value)}
              placeholder="user id"
            />
          </div>
        </div>
        <button className="primary" type="submit" disabled={busy || !name.trim()}>
          {busy ? "Creating…" : "Create team"}
        </button>
        <FormStatus ok={ok} err={err} />
      </form>
    </Card>
  );
}

// ── Add employee to team ────────────────────────────────────────────────────────
function AddTeamMemberForm() {
  const [teamId, setTeamId] = useState("");
  const [employeeId, setEmployeeId] = useState("");
  const [busy, setBusy] = useState(false);
  const [ok, setOk] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setOk(null);
    setErr(null);
    setBusy(true);
    try {
      const m = await api.addTeamMember(teamId.trim(), employeeId.trim());
      setOk(`Added employee ${m.employee_id} to team ${m.team_id}.`);
      setEmployeeId("");
    } catch (e2) {
      if (e2 instanceof ApiError && e2.status === 401) return;
      setErr(message(e2, "Failed to add team member."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card title="Add employee to team">
      <form onSubmit={submit}>
        <div className="row" style={{ marginBottom: 0 }}>
          <div className="field" style={{ flex: "1 1 220px" }}>
            <label htmlFor="member-team">Team id</label>
            <input
              id="member-team"
              value={teamId}
              onChange={(e) => setTeamId(e.target.value)}
              placeholder="team id"
              required
            />
          </div>
          <div className="field" style={{ flex: "1 1 220px" }}>
            <label htmlFor="member-emp">Employee id</label>
            <input
              id="member-emp"
              value={employeeId}
              onChange={(e) => setEmployeeId(e.target.value)}
              placeholder="employee id"
              required
            />
          </div>
        </div>
        <button className="primary" type="submit" disabled={busy || !teamId.trim() || !employeeId.trim()}>
          {busy ? "Adding…" : "Add member"}
        </button>
        <FormStatus ok={ok} err={err} />
      </form>
    </Card>
  );
}

// ── Enroll device ─────────────────────────────────────────────────────────────
function EnrollDeviceForm({ orgId }: { orgId: string }) {
  const [employeeId, setEmployeeId] = useState("");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [result, setResult] = useState<DeviceEnrollment | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setErr(null);
    setResult(null);
    if (!orgId) {
      setErr("Select an organization first.");
      return;
    }
    setBusy(true);
    try {
      const res = await api.enrollDevice(orgId, {
        employee_id: employeeId.trim(),
        name: name.trim(),
      });
      setResult(res);
      setEmployeeId("");
      setName("");
    } catch (e2) {
      if (e2 instanceof ApiError && e2.status === 401) return;
      setErr(message(e2, "Failed to enroll device."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card
      title="Enroll device"
      sub="Issue credentials for a company-owned workstation. The secret is shown once."
    >
      <form onSubmit={submit}>
        <div className="row" style={{ marginBottom: 0 }}>
          <div className="field" style={{ flex: "1 1 220px" }}>
            <label htmlFor="dev-emp">Employee id</label>
            <input
              id="dev-emp"
              value={employeeId}
              onChange={(e) => setEmployeeId(e.target.value)}
              placeholder="employee id"
              required
            />
          </div>
          <div className="field" style={{ flex: "1 1 220px" }}>
            <label htmlFor="dev-name">Device name</label>
            <input
              id="dev-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Jane's laptop"
              required
            />
          </div>
        </div>
        <button className="primary" type="submit" disabled={busy || !employeeId.trim() || !name.trim()}>
          {busy ? "Enrolling…" : "Enroll device"}
        </button>
        {err ? <FormStatus ok={null} err={err} /> : null}
      </form>

      {result ? (
        <div
          style={{
            marginTop: 16,
            border: "1px solid rgba(224, 166, 58, 0.5)",
            background: "rgba(224, 166, 58, 0.08)",
            borderRadius: "var(--radius)",
            padding: "14px 16px",
          }}
        >
          <div style={{ color: "var(--amber)", fontWeight: 700, marginBottom: 8 }}>
            Copy the device secret now — it cannot be retrieved again.
          </div>
          <div className="small muted" style={{ marginBottom: 10 }}>
            Device id: <span className="mono">{result.device_id}</span>
          </div>

          <div className="field" style={{ marginBottom: 10 }}>
            <label>Device key</label>
            <div className="row" style={{ flexWrap: "nowrap" }}>
              <input className="mono" readOnly value={result.device_key} />
              <CopyButton value={result.device_key} />
            </div>
          </div>

          <div className="field" style={{ marginBottom: 0 }}>
            <label>Device secret (shown once)</label>
            <div className="row" style={{ flexWrap: "nowrap" }}>
              <input className="mono" readOnly value={result.device_secret} />
              <CopyButton value={result.device_secret} />
            </div>
          </div>

          {result.note ? (
            <div className="small muted" style={{ marginTop: 10 }}>
              {result.note}
            </div>
          ) : null}
        </div>
      ) : null}
    </Card>
  );
}

// ── Revoke device ────────────────────────────────────────────────────────────────
function RevokeDeviceForm() {
  const [deviceId, setDeviceId] = useState("");
  const [busy, setBusy] = useState(false);
  const [ok, setOk] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setOk(null);
    setErr(null);
    setBusy(true);
    try {
      const res = await api.revokeDevice(deviceId.trim());
      setOk(`Device ${res.id} is now ${res.is_active ? "active" : "revoked"}.`);
      setDeviceId("");
    } catch (e2) {
      if (e2 instanceof ApiError && e2.status === 401) return;
      setErr(message(e2, "Failed to revoke device."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card title="Revoke device" sub="Immediately disable a device's credentials.">
      <form onSubmit={submit}>
        <div className="field">
          <label htmlFor="revoke-dev">Device id</label>
          <input
            id="revoke-dev"
            value={deviceId}
            onChange={(e) => setDeviceId(e.target.value)}
            placeholder="device id"
            required
          />
        </div>
        <button className="primary" type="submit" disabled={busy || !deviceId.trim()}>
          {busy ? "Revoking…" : "Revoke device"}
        </button>
        <FormStatus ok={ok} err={err} />
      </form>
    </Card>
  );
}

// ── Allowlist ──────────────────────────────────────────────────────────────────
function AllowlistForm({ orgId }: { orgId: string }) {
  const [domains, setDomains] = useState("");
  const [busy, setBusy] = useState(false);
  const [ok, setOk] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setOk(null);
    setErr(null);
    if (!orgId) {
      setErr("Select an organization first.");
      return;
    }
    setBusy(true);
    try {
      const res = await api.setAllowlist(orgId, parseDomains(domains));
      setOk(
        `Allowlist updated (${res.allowlisted_domains.length} domain${
          res.allowlisted_domains.length === 1 ? "" : "s"
        }).`
      );
    } catch (e2) {
      if (e2 instanceof ApiError && e2.status === 401) return;
      setErr(message(e2, "Failed to update allowlist."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card
      title="Content-capture allowlist"
      sub="Only these business domains may capture business text. Comma or newline separated."
    >
      <form onSubmit={submit}>
        <div className="field">
          <label htmlFor="allowlist">Allowlisted domains</label>
          <textarea
            id="allowlist"
            rows={4}
            value={domains}
            onChange={(e) => setDomains(e.target.value)}
            placeholder={"docs.google.com\ncrm.acme.com"}
          />
        </div>
        <button className="primary" type="submit" disabled={busy}>
          {busy ? "Saving…" : "Save allowlist"}
        </button>
        <FormStatus ok={ok} err={err} />
      </form>
    </Card>
  );
}

/** Split a comma- or newline-separated domain list into trimmed, non-empty parts. */
function parseDomains(value: string): string[] {
  return value
    .split(/[\n,]/)
    .map((s) => s.trim())
    .filter((s) => s.length > 0);
}

function AdminInner() {
  const { me, activeOrgId, organizations, selectOrg, refreshOrganizations } = useAuth();

  if (!me) return <Loading label="Loading your profile…" />;

  if (!isAdminRole(me.role)) {
    return (
      <>
        <h1 className="page-title">Admin</h1>
        <ErrorNotice message="You are not authorized to view this page." />
      </>
    );
  }

  const isSuper = me.role === "SUPER_ADMIN";
  const orgId = activeOrgId ?? "";
  const activeOrgName = organizations?.find((o) => o.id === orgId)?.name;

  async function onOrgCreated(org: OrganizationSummary) {
    try {
      await refreshOrganizations();
    } catch {
      /* the top-bar list refreshes on the next load */
    }
    selectOrg(org.id);
  }

  return (
    <>
      <h1 className="page-title">Admin &amp; provisioning</h1>
      <p className="page-sub">
        Create users, employees, teams and devices, and manage the content-capture allowlist.
      </p>

      {isSuper ? (
        <>
          <CreateOrgForm onCreated={(org) => void onOrgCreated(org)} />
          <div className="card">
            <h2>Active organization</h2>
            <p className="muted small" style={{ margin: 0 }}>
              {orgId ? (
                <>
                  Actions below apply to <strong>{activeOrgName ?? orgId}</strong>{" "}
                  <span className="mono">({orgId})</span>. Switch organizations in the top bar.
                </>
              ) : (
                "Choose an organization in the top bar, or create one above."
              )}
            </p>
          </div>
        </>
      ) : (
        <div className="card">
          <h2>Organization</h2>
          <p className="muted small" style={{ margin: 0 }}>
            Actions apply to your organization:{" "}
            <span className="mono">{me.organization_id ?? "—"}</span>
          </p>
        </div>
      )}

      {isSuper && !orgId ? (
        <div className="notice" style={{ marginBottom: 20 }}>
          Choose (or create) an organization to enable the forms below.
        </div>
      ) : null}

      <CreateUserForm orgId={orgId} />
      <CreateEmployeeForm orgId={orgId} />
      <CreateTeamForm orgId={orgId} />
      <AddTeamMemberForm />
      <EnrollDeviceForm orgId={orgId} />
      <RevokeDeviceForm />
      <AllowlistForm orgId={orgId} />
    </>
  );
}

export default function AdminPage() {
  return (
    <Protected>
      <AdminInner />
    </Protected>
  );
}
