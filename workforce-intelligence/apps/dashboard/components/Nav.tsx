"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { isAdminRole, useAuth } from "@/lib/auth";

const LINKS = [
  { href: "/", label: "Overview" },
  { href: "/analytics", label: "Analytics" },
  { href: "/ai", label: "AI Assistant" },
];

// Shown only to ORG_ADMIN / SUPER_ADMIN.
const ADMIN_LINKS = [
  { href: "/admin", label: "Admin" },
  { href: "/integrations", label: "Integrations" },
  { href: "/audit", label: "Audit" },
];

export function Nav() {
  const pathname = usePathname();
  const { token, me, logout } = useAuth();

  // No chrome on the login screen.
  if (pathname === "/login") return null;

  const isActive = (href: string) =>
    href === "/" ? pathname === "/" : pathname.startsWith(href);

  const links = isAdminRole(me?.role) ? [...LINKS, ...ADMIN_LINKS] : LINKS;

  return (
    <header className="app-header">
      <div className="app-header-inner">
        <Link href="/" className="brand">
          Workforce<span>Intelligence</span>
        </Link>

        {token ? (
          <>
            <nav className="nav-links">
              {links.map((l) => (
                <Link
                  key={l.href}
                  href={l.href}
                  className={`nav-link${isActive(l.href) ? " active" : ""}`}
                >
                  {l.label}
                </Link>
              ))}
            </nav>
            <div className="nav-right">
              {me ? (
                <span className="small">
                  {me.full_name || me.email}
                  {me.role ? ` · ${me.role}` : ""}
                </span>
              ) : null}
              <button className="small-btn ghost" onClick={logout}>
                Log out
              </button>
            </div>
          </>
        ) : (
          <nav className="nav-links" />
        )}
      </div>
    </header>
  );
}
