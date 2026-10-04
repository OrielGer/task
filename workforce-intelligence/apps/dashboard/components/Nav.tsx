"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { useAuth } from "@/lib/auth";

const LINKS = [
  { href: "/", label: "Overview" },
  { href: "/analytics", label: "Analytics" },
  { href: "/ai", label: "AI Assistant" },
];

export function Nav() {
  const pathname = usePathname();
  const { token, me, logout } = useAuth();

  // No chrome on the login screen.
  if (pathname === "/login") return null;

  const isActive = (href: string) =>
    href === "/" ? pathname === "/" : pathname.startsWith(href);

  return (
    <header className="app-header">
      <div className="app-header-inner">
        <Link href="/" className="brand">
          Workforce<span>Intelligence</span>
        </Link>

        {token ? (
          <>
            <nav className="nav-links">
              {LINKS.map((l) => (
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
