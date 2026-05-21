"use client";

import { useCallback, useEffect, useState } from "react";
import { editArticle, extractReferences, getArticle, trashArticle, type ScreeningStats } from "@/lib/api";
import type { Article } from "@/lib/types";

const DECISIONS = [
  ["unscreened", "Unscreened", "var(--muted)"],
  ["include", "Include", "#16a34a"],
  ["maybe", "Maybe", "#d97706"],
  ["exclude", "Exclude", "#dc2626"],
] as const;

export default function ArticleModal({
  articleId,
  initial,
  startInEdit = false,
  stats,
  position,
  onPrev,
  onNext,
  hasPrev = false,
  hasNext = false,
  onDelete,
  onClose,
  onChanged,
}: {
  articleId: number;
  initial?: Article | null;
  startInEdit?: boolean;
  stats?: ScreeningStats | null;
  position?: { index: number; total: number };
  onPrev?: () => void;
  onNext?: () => void;
  hasPrev?: boolean;
  hasNext?: boolean;
  onDelete?: () => void;
  onClose: () => void;
  onChanged?: () => void;
}) {
  const [a, setA] = useState<Article | null>(initial ?? null);
  const [editing, setEditing] = useState(startInEdit);
  const [draft, setDraft] = useState<Partial<Article>>(initial ?? {});
  const [busy, setBusy] = useState(false);
  const [loadingRefs, setLoadingRefs] = useState(false);

  // Always fetch fresh detail (incl. persisted references).
  useEffect(() => {
    getArticle(articleId, true).then((x) => {
      setA(x);
      setDraft(x);
    });
  }, [articleId]);

  const decide = useCallback(
    async (status: string) => {
      const { article } = await editArticle(articleId, { screening_status: status });
      setA(article);
      setDraft(article);
      onChanged?.();
    },
    [articleId, onChanged],
  );

  // Esc to close; i/m/e/u to set decision (when not editing / not typing).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !editing) return onClose();
      if (editing) return;
      const el = document.activeElement as HTMLElement | null;
      if (el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA")) return;
      if (e.key === "ArrowLeft" && hasPrev) {
        e.preventDefault();
        return onPrev?.();
      }
      if (e.key === "ArrowRight" && hasNext) {
        e.preventDefault();
        return onNext?.();
      }
      const map: Record<string, string> = { i: "include", m: "maybe", e: "exclude", u: "unscreened" };
      const status = map[e.key.toLowerCase()];
      if (status) {
        e.preventDefault();
        decide(status);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [editing, onClose, decide, hasPrev, hasNext, onPrev, onNext]);

  const save = useCallback(async () => {
    if (!a) return;
    const patch: Partial<Article> = {};
    (["title", "authors", "year", "doi", "abstract", "pub_type", "venue"] as const).forEach((k) => {
      if (draft[k] !== a[k]) (patch as Record<string, unknown>)[k] = draft[k];
    });
    if (Object.keys(patch).length === 0) {
      setEditing(false);
      return;
    }
    setBusy(true);
    try {
      const { article } = await editArticle(articleId, patch);
      setA(article);
      setDraft(article);
      setEditing(false);
      onChanged?.();
    } finally {
      setBusy(false);
    }
  }, [a, draft, articleId, onChanged]);

  const extract = useCallback(async () => {
    setLoadingRefs(true);
    try {
      const res = await extractReferences(articleId);
      setA((d) => (d ? { ...d, references: res.references, references_count: res.count } : d));
    } catch (e) {
      setA((d) => (d ? { ...d, references_error: String(e) } : d));
    } finally {
      setLoadingRefs(false);
    }
  }, [articleId]);

  const remove = useCallback(async () => {
    setBusy(true);
    await trashArticle(articleId);
    onChanged?.();
    onClose();
  }, [articleId, onChanged, onClose]);

  const set = (k: keyof Article, v: unknown) => setDraft((d) => ({ ...d, [k]: v }));

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center gap-3 bg-black/50 p-4 backdrop-blur-sm"
      onClick={() => !editing && onClose()}
    >
      {/* Prev — vertically centered, with the live panel docked just above it */}
      <div className="relative hidden shrink-0 self-center sm:block" onClick={(e) => e.stopPropagation()}>
        <div className="absolute bottom-full right-0 mb-3 w-40">
          <ScreenPanel stats={stats} position={position} />
        </div>
        <button
          className="btn flex w-24 items-center justify-center py-2 disabled:opacity-30"
          onClick={(e) => {
            e.stopPropagation();
            onPrev?.();
          }}
          disabled={!hasPrev}
          title="Previous (←)"
        >
          ‹ Prev
        </button>
      </div>

      <div
        className="card my-4 max-h-[90vh] w-full max-w-3xl overflow-hidden p-0 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {!a ? (
          <div className="p-8">
            <div className="h-6 w-2/3 animate-pulse rounded bg-[var(--bg)]" />
            <div className="mt-4 h-24 animate-pulse rounded bg-[var(--bg)]" />
          </div>
        ) : (
          <>
            {/* Header */}
            <div className="flex items-start justify-between gap-4 border-b p-5">
              <div className="min-w-0 flex-1">
                {editing ? (
                  <textarea
                    className="input w-full text-base font-semibold"
                    rows={2}
                    value={draft.title ?? ""}
                    onChange={(e) => set("title", e.target.value)}
                  />
                ) : (
                  <h2 className="text-lg font-semibold leading-snug">{a.title}</h2>
                )}
                {!editing && (
                  <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-[var(--muted)]">
                    {a.year != null && <span className="tabular-nums">{a.year}</span>}
                    {a.venue && <span className="italic">{a.venue}</span>}
                    {a.category && <span>· {a.category}</span>}
                    {a.citation_count != null && <span>· {a.citation_count.toLocaleString()} cites</span>}
                    {a.source && <span>· {a.source}</span>}
                  </div>
                )}
              </div>
              <button
                className="shrink-0 rounded-md px-2 py-1 text-sm text-[var(--muted)] hover:bg-[var(--surface-2)] hover:text-[var(--text)]"
                onClick={onClose}
                aria-label="Close"
              >
                ✕
              </button>
            </div>

            {/* Screening decision */}
            <div className="flex items-center gap-2 border-b px-5 py-3">
              <span className="text-xs font-medium uppercase tracking-wide text-[var(--muted)]">Decision</span>
              <div className="flex overflow-hidden rounded-md border">
                {DECISIONS.map(([val, label, color]) => {
                  const active = (a.screening_status || "unscreened") === val;
                  return (
                    <button
                      key={val}
                      onClick={() => decide(val)}
                      className="border-r px-3 py-1 text-xs font-medium transition last:border-r-0"
                      style={
                        active
                          ? { background: color, color: val === "unscreened" ? "var(--text)" : "#fff" }
                          : { color: "var(--muted)" }
                      }
                    >
                      {label}
                    </button>
                  );
                })}
              </div>
              {a.edited_by_user && <span className="badge badge-edited ml-auto">edited</span>}
            </div>

            {/* Body */}
            <div className="max-h-[55vh] overflow-y-auto p-5">
              {editing ? (
                <div className="space-y-3">
                  <Field label="Authors">
                    <input className="input w-full" value={draft.authors ?? ""} onChange={(e) => set("authors", e.target.value)} />
                  </Field>
                  <div className="flex gap-3">
                    <Field label="Year">
                      <input
                        className="input w-28"
                        inputMode="numeric"
                        value={draft.year ?? ""}
                        onChange={(e) => set("year", e.target.value ? Number(e.target.value.replace(/\D/g, "")) : null)}
                      />
                    </Field>
                    <Field label="Type">
                      <input className="input w-40" value={draft.pub_type ?? ""} onChange={(e) => set("pub_type", e.target.value)} />
                    </Field>
                  </div>
                  <Field label="Journal">
                    <input className="input w-full" value={draft.venue ?? ""} onChange={(e) => set("venue", e.target.value)} />
                  </Field>
                  <Field label="DOI">
                    <input className="input w-full" value={draft.doi ?? ""} onChange={(e) => set("doi", e.target.value)} />
                  </Field>
                  <Field label="Abstract">
                    <textarea
                      className="input min-h-[160px] w-full leading-relaxed"
                      value={draft.abstract ?? ""}
                      onChange={(e) => set("abstract", e.target.value)}
                    />
                  </Field>
                </div>
              ) : (
                <>
                  {a.authors && <p className="text-sm text-[var(--muted)]">{a.authors}</p>}
                  {a.doi && (
                    <a
                      href={`https://doi.org/${a.doi}`}
                      target="_blank"
                      rel="noreferrer"
                      className="mt-1 inline-block text-xs text-[var(--primary)] hover:underline"
                    >
                      https://doi.org/{a.doi} ↗
                    </a>
                  )}
                  <div className="mt-4">
                    <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-[var(--muted)]">Abstract</div>
                    {a.abstract ? (
                      <p className="whitespace-pre-line text-sm leading-relaxed">{a.abstract}</p>
                    ) : (
                      <p className="text-sm italic text-[var(--muted)]">
                        {a.abstract_unavailable ? "No open abstract (publisher-restricted)." : "No abstract available."}
                      </p>
                    )}
                  </div>

                  {/* References — manual, per-paper. The user chooses to pull
                      this one paper's reference list; nothing happens on its own. */}
                  <div className="mt-5 border-t pt-4">
                    <div className="mb-2 flex items-center justify-between">
                      <div className="text-xs font-semibold uppercase tracking-wide text-[var(--muted)]">
                        References {a.references_count ? `(${a.references_count})` : ""}
                      </div>
                      {a.references && a.references.length > 0 ? (
                        <button
                          className="text-xs text-[var(--muted)] hover:text-[var(--text)] disabled:opacity-40"
                          onClick={extract}
                          disabled={loadingRefs || !a.doi}
                          title="Re-fetch this paper's references now"
                        >
                          {loadingRefs ? "Refreshing…" : "↻ Refresh"}
                        </button>
                      ) : (
                        <button
                          className="btn px-2 py-1 text-xs disabled:opacity-40"
                          onClick={extract}
                          disabled={loadingRefs || !a.doi}
                          title="Collect this paper's reference list now"
                        >
                          {loadingRefs ? "Collecting…" : "Collect references"}
                        </button>
                      )}
                    </div>
                    {a.references_error && <div className="text-xs text-[#b91c1c]">{a.references_error}</div>}
                    {a.references && a.references.length > 0 && (
                      <ol className="max-h-48 list-decimal space-y-1 overflow-y-auto pl-5 text-xs text-[var(--muted)]">
                        {a.references.slice(0, 200).map((r, i) => (
                          <li key={i}>
                            {r.title || r.doi || "—"} {r.year ? `(${r.year})` : ""}
                          </li>
                        ))}
                      </ol>
                    )}
                    {!a.doi && <div className="text-xs italic text-[var(--muted)]">No DOI — references can&apos;t be collected.</div>}
                  </div>
                </>
              )}
            </div>

            {/* Footer */}
            <div className="flex items-center justify-between gap-2 border-t p-4">
              <button className="btn text-[#b91c1c]" onClick={() => (onDelete ? onDelete() : remove())} disabled={busy}>
                Delete
              </button>
              <div className="flex gap-2">
                {editing ? (
                  <>
                    <button className="btn" onClick={() => { setEditing(false); setDraft(a); }} disabled={busy}>
                      Cancel
                    </button>
                    <button className="btn btn-primary" onClick={save} disabled={busy}>
                      {busy ? "Saving…" : "Save"}
                    </button>
                  </>
                ) : (
                  <>
                    <button className="btn" onClick={onClose}>
                      Close
                    </button>
                    <button className="btn btn-primary" onClick={() => setEditing(true)}>
                      Edit
                    </button>
                  </>
                )}
              </div>
            </div>
          </>
        )}
      </div>

      {/* Next — narrow, vertically centered (same level as Prev) */}
      <button
        className="btn hidden w-24 shrink-0 items-center justify-center self-center py-2 disabled:opacity-30 sm:flex"
        onClick={(e) => {
          e.stopPropagation();
          onNext?.();
        }}
        disabled={!hasNext}
        title="Next (→)"
      >
        Next ›
      </button>
    </div>
  );
}

function ScreenPanel({
  stats,
  position,
}: {
  stats?: ScreeningStats | null;
  position?: { index: number; total: number };
}) {
  const screened = stats ? stats.include + stats.maybe + stats.exclude : 0;
  const pct = stats && stats.total ? Math.round((screened / stats.total) * 100) : 0;
  const rows: [string, number, string][] = stats
    ? [
        ["Include", stats.include, "#16a34a"],
        ["Maybe", stats.maybe, "#d97706"],
        ["Exclude", stats.exclude, "#dc2626"],
        ["Unscreened", stats.unscreened, "var(--muted)"],
      ]
    : [];
  return (
    <div className="card p-4">
      {position && (
        <div className="mb-3 border-b pb-3">
          <div className="text-xs uppercase tracking-wide text-[var(--muted)]">Reviewing</div>
          <div className="text-lg font-semibold tabular-nums">
            {position.index + 1} <span className="text-sm font-normal text-[var(--muted)]">/ {position.total}</span>
          </div>
        </div>
      )}
      <div className="mb-1 flex items-center justify-between text-xs">
        <span className="font-semibold uppercase tracking-wide text-[var(--muted)]">Screened</span>
        <span className="tabular-nums text-[var(--muted)]">{pct}%</span>
      </div>
      <div className="mb-3 h-1.5 overflow-hidden rounded-full bg-[var(--bg)]">
        <div className="h-full rounded-full bg-[var(--primary)] transition-all" style={{ width: `${pct}%` }} />
      </div>
      <div className="space-y-1.5">
        {rows.map(([label, n, color]) => (
          <div key={label} className="flex items-center justify-between text-sm">
            <span className="flex items-center gap-1.5 text-[var(--muted)]">
              <span className="h-2 w-2 rounded-full" style={{ background: color }} />
              {label}
            </span>
            <span className="tabular-nums font-medium">{n.toLocaleString()}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-medium text-[var(--muted)]">{label}</span>
      {children}
    </label>
  );
}
