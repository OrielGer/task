"use client";

import { useEffect, useMemo, useState } from "react";

import { api, ApiError } from "@/lib/api";
import { Loading, ErrorNotice } from "@/components/ui";
import { diffLines, diffStats } from "@/lib/diff";
import { formatDateTime } from "@/lib/format";
import type { ContentItem, ContentVersion } from "@/lib/types";

function isAbort(err: unknown): boolean {
  return err instanceof DOMException && err.name === "AbortError";
}

/** Renders a line diff from `before` -> `after`. Content is already redacted. */
function VersionDiff({ before, after }: { before: ContentVersion; after: ContentVersion }) {
  const lines = useMemo(() => diffLines(before.content, after.content), [before, after]);
  const stats = diffStats(lines);
  const labelOf = (v: ContentVersion) =>
    v.is_final ? "final" : `v${v.version_number}`;

  return (
    <div style={{ marginBottom: 16 }}>
      <div className="small muted" style={{ marginBottom: 6 }}>
        {labelOf(before)} → {labelOf(after)}{" "}
        <span style={{ color: "var(--green)" }}>+{stats.added}</span>{" "}
        <span style={{ color: "var(--red)" }}>−{stats.removed}</span>
      </div>
      <div className="diff">
        {lines.map((l, i) => {
          const cls =
            l.type === "add" ? "diff-line diff-add" : l.type === "remove" ? "diff-line diff-remove" : "diff-line";
          const gutter = l.type === "add" ? "+" : l.type === "remove" ? "−" : " ";
          return (
            <div className={cls} key={i}>
              <span className="diff-gutter">{gutter}</span>
              <span>{l.text}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function VersionHistory({ employeeId, itemId }: { employeeId: string; itemId: string }) {
  const [versions, setVersions] = useState<ContentVersion[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setVersions(null);
    setError(null);
    api
      .contentVersions(employeeId, itemId, controller.signal)
      .then(setVersions)
      .catch((err) => {
        if (isAbort(err)) return;
        if (err instanceof ApiError && err.status === 401) return;
        setError(err instanceof Error ? err.message : "Failed to load versions.");
      });
    return () => controller.abort();
  }, [employeeId, itemId]);

  if (error) return <ErrorNotice message={error} />;
  if (!versions) return <Loading label="Loading version history…" />;
  if (versions.length === 0) return <div className="notice">No versions recorded.</div>;

  // Ensure chronological order (v1 → v2 → … → final).
  const ordered = [...versions].sort((a, b) => a.version_number - b.version_number);

  return (
    <div style={{ marginTop: 10, paddingLeft: 12, borderLeft: "2px solid var(--border)" }}>
      <div className="small muted" style={{ marginBottom: 10 }}>
        {ordered.length} version{ordered.length === 1 ? "" : "s"}
      </div>

      {ordered.length === 1 ? (
        <div className="diff">
          {ordered[0].content.split("\n").map((line, i) => (
            <div className="diff-line" key={i}>
              <span className="diff-gutter"> </span>
              <span>{line}</span>
            </div>
          ))}
        </div>
      ) : (
        ordered
          .slice(1)
          .map((v, i) => (
            <VersionDiff key={v.id} before={ordered[i]} after={v} />
          ))
      )}
    </div>
  );
}

export function ContentPanel({ employeeId }: { employeeId: string }) {
  const [items, setItems] = useState<ContentItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    api
      .content(employeeId, controller.signal)
      .then(setItems)
      .catch((err) => {
        if (isAbort(err)) return;
        if (err instanceof ApiError && err.status === 401) return;
        setError(err instanceof Error ? err.message : "Failed to load content.");
      });
    return () => controller.abort();
  }, [employeeId]);

  if (error) return <ErrorNotice message={error} />;
  if (!items) return <Loading />;
  if (items.length === 0)
    return <div className="notice">No business content captured for this employee.</div>;

  return (
    <div>
      <p className="small muted" style={{ marginTop: 0 }}>
        Captured from allowlisted business domains. Content shown is already redacted server-side.
      </p>
      {items.map((item) => {
        const open = openId === item.id;
        return (
          <div
            key={item.id}
            style={{
              border: "1px solid var(--border)",
              borderRadius: 8,
              padding: "12px 14px",
              marginBottom: 10,
            }}
          >
            <div
              className="row"
              style={{ justifyContent: "space-between", cursor: "pointer" }}
              onClick={() => setOpenId(open ? null : item.id)}
            >
              <div>
                <strong>{item.content_type || item.source || "Content item"}</strong>
                <div className="small faint">
                  {item.domain}
                  {item.external_reference ? ` · ${item.external_reference}` : ""}
                </div>
              </div>
              <div className="row small">
                <span className="muted">{formatDateTime(item.updated_at)}</span>
                <button className="small-btn ghost" onClick={(e) => { e.stopPropagation(); setOpenId(open ? null : item.id); }}>
                  {open ? "Hide history" : "Version history"}
                </button>
              </div>
            </div>
            {open ? <VersionHistory employeeId={employeeId} itemId={item.id} /> : null}
          </div>
        );
      })}
    </div>
  );
}
