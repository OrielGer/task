"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";

import { api, ApiError } from "@/lib/api";
import { Protected } from "@/components/Protected";
import { ErrorNotice } from "@/components/ui";

interface Turn {
  id: number;
  question: string;
  answer: string | null;
  provider?: string;
  usedScope?: string;
  error?: string;
}

function AiInner() {
  const [question, setQuestion] = useState("");
  const [employeeId, setEmployeeId] = useState("");
  const [teamId, setTeamId] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const nextId = useRef(1);
  const transcriptEnd = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    transcriptEnd.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns]);

  async function ask(e: FormEvent) {
    e.preventDefault();
    const q = question.trim();
    if (!q || busy) return;
    setError(null);

    const id = nextId.current++;
    setTurns((prev) => [...prev, { id, question: q, answer: null }]);
    setQuestion("");
    setBusy(true);

    try {
      const res = await api.aiQuery({
        question: q,
        employee_id: employeeId.trim() || undefined,
        team_id: teamId.trim() || undefined,
      });
      setTurns((prev) =>
        prev.map((t) =>
          t.id === id
            ? { ...t, answer: res.answer, provider: res.provider, usedScope: res.used_scope }
            : t
        )
      );
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) return;
      const message = err instanceof Error ? err.message : "The AI query failed.";
      setTurns((prev) => prev.map((t) => (t.id === id ? { ...t, error: message } : t)));
      setError(message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <h1 className="page-title">AI assistant</h1>
      <p className="page-sub">
        Ask natural-language questions about activity and workflows. Answers are produced
        server-side from already-redacted data; the scope used is shown with each reply.
      </p>

      <div className="card">
        <div className="row" style={{ marginBottom: 14 }}>
          <div style={{ flex: "1 1 220px" }}>
            <label htmlFor="emp">Scope to employee (optional)</label>
            <input
              id="emp"
              placeholder="employee id"
              value={employeeId}
              onChange={(e) => setEmployeeId(e.target.value)}
            />
          </div>
          <div style={{ flex: "1 1 220px" }}>
            <label htmlFor="team">Scope to team (optional)</label>
            <input
              id="team"
              placeholder="team id"
              value={teamId}
              onChange={(e) => setTeamId(e.target.value)}
            />
          </div>
        </div>

        {turns.length === 0 ? (
          <div className="notice" style={{ marginBottom: 16 }}>
            No messages yet. Try “What did the sales team spend the most time on this week?”
          </div>
        ) : (
          <div className="chat">
            {turns.map((t) => (
              <div key={t.id} style={{ display: "contents" }}>
                <div className="msg msg-user">{t.question}</div>
                {t.answer !== null ? (
                  <div className="msg msg-ai">
                    {t.answer}
                    <div className="msg-meta">
                      scope: {t.usedScope ?? "—"} · provider: {t.provider ?? "—"}
                    </div>
                  </div>
                ) : t.error ? (
                  <div className="msg msg-ai" style={{ color: "var(--red)" }}>
                    {t.error}
                  </div>
                ) : (
                  <div className="msg msg-ai muted">Thinking…</div>
                )}
              </div>
            ))}
            <div ref={transcriptEnd} />
          </div>
        )}

        {error ? <ErrorNotice message={error} /> : null}

        <form onSubmit={ask} className="row" style={{ marginTop: 14, flexWrap: "nowrap" }}>
          <input
            placeholder="Ask a question…"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            disabled={busy}
          />
          <button className="primary" type="submit" disabled={busy || !question.trim()}>
            {busy ? "…" : "Send"}
          </button>
        </form>
      </div>
    </>
  );
}

export default function AiPage() {
  return (
    <Protected>
      <AiInner />
    </Protected>
  );
}
