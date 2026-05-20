"use client";

import { useCallback, useEffect, useState } from "react";
import { editArticle, getArticle, listArticles, trashArticle } from "@/lib/api";
import type { Article } from "@/lib/types";

const DECISIONS = ["unscreened", "include", "maybe", "exclude"] as const;

export default function ReadReview({ projectId }: { projectId: number }) {
  const [list, setList] = useState<Article[]>([]);
  const [q, setQ] = useState("");
  const [journal, setJournal] = useState("");
  const [yearMin, setYearMin] = useState("");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [detail, setDetail] = useState<Article | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [loadingRefs, setLoadingRefs] = useState(false);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<Partial<Article>>({});

  const reload = useCallback(() => {
    return listArticles(projectId, {
      q,
      journal,
      year_min: yearMin ? Number(yearMin) : undefined,
      limit: 200,
    }).then((r) => {
      setList(r.items);
      return r.items;
    });
  }, [projectId, q, journal, yearMin]);

  useEffect(() => {
    const h = setTimeout(() => {
      reload().then((items) => {
        if (items.length && (selectedId === null || !items.some((a) => a.id === selectedId))) {
          setSelectedId(items[0].id);
        }
      });
    }, 250);
    return () => clearTimeout(h);
  }, [reload]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (selectedId === null) return;
    setLoadingDetail(true);
    setEditing(false);
    getArticle(selectedId, false)
      .then((a) => {
        setDetail(a);
        setDraft(a);
      })
      .finally(() => setLoadingDetail(false));
  }, [selectedId]);

  const decide = useCallback(
    async (status: string) => {
      if (!detail) return;
      const { article } = await editArticle(detail.id, { screening_status: status });
      setDetail(article);
      setDraft(article);
      setList((prev) => prev.map((a) => (a.id === article.id ? { ...a, screening_status: status } : a)));
    },
    [detail],
  );

  const save = useCallback(async () => {
    if (!detail) return;
    const patch: Partial<Article> = {};
    (["title", "authors", "year", "doi", "url", "abstract", "pub_type", "tags", "notes"] as const).forEach((k) => {
      if (draft[k] !== detail[k]) (patch as Record<string, unknown>)[k] = draft[k];
    });
    if (Object.keys(patch).length === 0) {
      setEditing(false);
      return;
    }
    const { article } = await editArticle(detail.id, patch);
    setDetail(article);
    setDraft(article);
    setEditing(false);
    setList((prev) => prev.map((a) => (a.id === article.id ? { ...a, title: article.title } : a)));
  }, [detail, draft]);

  const loadRefs = useCallback(async () => {
    if (!detail) return;
    setLoadingRefs(true);
    try {
      const full = await getArticle(detail.id, true);
      setDetail((d) => (d ? { ...d, references: full.references, references_error: full.references_error } : d));
    } finally {
      setLoadingRefs(false);
    }
  }, [detail]);

  const trash = useCallback(async () => {
    if (!detail) return;
    await trashArticle(detail.id);
    const removedId = detail.id;
    const items = await reload();
    const next = items.find((a) => a.id !== removedId);
    setSelectedId(next ? next.id : null);
    if (!next) setDetail(null);
  }, [detail, reload]);

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(300px,380px)_1fr]">
      {/* Left: list */}
      <div className="card flex max-h-[78vh] flex-col overflow-hidden">
        <div className="space-y-2 border-b p-2">
          <input className="input" placeholder="Filter by title…" value={q} onChange={(e) => setQ(e.target.value)} />
          <div className="flex gap-2">
            <input className="input" placeholder="Journal contains…" value={journal} onChange={(e) => setJournal(e.target.value)} />
            <input
              className="input max-w-[110px]"
              type="number"
              placeholder="Year ≥"
              value={yearMin}
              onChange={(e) => setYearMin(e.target.value)}
            />
          </div>
        </div>
        <div className="flex-1 overflow-y-auto">
          {list.map((a) => (
            <button
              key={a.id}
              onClick={() => setSelectedId(a.id)}
              className={`block w-full border-b px-3 py-2 text-left transition hover:bg-[var(--surface-2)] ${
                a.id === selectedId ? "bg-[var(--primary-weak)]" : ""
              }`}
            >
              <div className="line-clamp-2 text-sm font-medium">{a.title}</div>
              {a.venue && <div className="mt-0.5 line-clamp-1 text-xs italic text-[var(--muted)]">{a.venue}</div>}
              <div className="mt-1 flex items-center gap-2 text-xs text-[var(--muted)]">
                <span>{a.year ?? "—"}</span>
                {a.citation_count != null && <span>· {a.citation_count.toLocaleString()} cites</span>}
                <DecisionDot value={a.screening_status} />
                {a.edited_by_user && <span className="badge badge-edited">edited</span>}
              </div>
            </button>
          ))}
          {list.length === 0 && (
            <div className="p-6 text-center text-sm text-[var(--muted)]">No papers.</div>
          )}
        </div>
      </div>

      {/* Right: detail */}
      <div className="card max-h-[75vh] overflow-y-auto p-5">
        {loadingDetail && <div className="h-40 animate-pulse rounded bg-[var(--bg)]" />}
        {!loadingDetail && detail && (
          <div>
            <div className="mb-3 flex items-start justify-between gap-3">
              <div className="flex flex-wrap items-center gap-2">
                <DecisionBadge value={detail.screening_status} />
                {detail.edited_by_user && <span className="badge badge-edited">user-edited</span>}
                {detail.pub_type && <span className="badge">{detail.pub_type}</span>}
                <span className="badge">{detail.source}</span>
              </div>
              <div className="flex gap-2">
                <button className="btn btn-ghost" onClick={() => setEditing((v) => !v)}>
                  {editing ? "Cancel" : "Edit"}
                </button>
                <button
                  className="btn"
                  style={{ color: "#b91c1c", borderColor: "#fecaca" }}
                  onClick={trash}
                  title="Move to trash (collected by mistake / wrong field). Different from 'exclude'."
                >
                  Delete
                </button>
              </div>
            </div>

            {editing ? (
              <EditForm draft={draft} setDraft={setDraft} onSave={save} />
            ) : (
              <ReadView detail={detail} />
            )}

            <div className="mt-5 border-t pt-4">
              <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--muted)]">
                Screening decision
              </div>
              <div className="flex gap-2">
                {DECISIONS.map((d) => (
                  <button
                    key={d}
                    className={`btn ${detail.screening_status === d ? "btn-primary" : ""}`}
                    onClick={() => decide(d)}
                  >
                    {d}
                  </button>
                ))}
              </div>
            </div>

            <div className="mt-5 border-t pt-4">
              <div className="mb-2 flex items-center justify-between">
                <div className="text-xs font-semibold uppercase tracking-wide text-[var(--muted)]">
                  References {detail.references ? `(${detail.references.length})` : ""}
                </div>
                {!detail.references && (
                  <button className="btn" onClick={loadRefs} disabled={loadingRefs || !detail.doi}>
                    {loadingRefs ? "Loading…" : detail.doi ? "Load references" : "No DOI"}
                  </button>
                )}
              </div>
              {detail.references_error && (
                <div className="text-xs text-[#b91c1c]">{detail.references_error}</div>
              )}
              {detail.references && detail.references.length > 0 && (
                <ol className="space-y-1.5">
                  {detail.references.slice(0, 200).map((r, i) => (
                    <li key={i} className="text-xs">
                      <span className="text-[var(--muted)]">{r.year ?? "—"} · </span>
                      {r.doi ? (
                        <a className="text-[var(--primary)] hover:underline" href={`https://doi.org/${r.doi}`} target="_blank" rel="noreferrer">
                          {r.title || r.doi}
                        </a>
                      ) : (
                        <span>{r.title}</span>
                      )}
                      {r.is_review && <span className="badge ml-1">review</span>}
                    </li>
                  ))}
                </ol>
              )}
            </div>
          </div>
        )}
        {!loadingDetail && !detail && (
          <div className="grid h-40 place-items-center text-sm text-[var(--muted)]">
            Select a paper to review.
          </div>
        )}
      </div>
    </div>
  );
}

function ReadView({ detail }: { detail: Article }) {
  return (
    <div>
      <h2 className="text-lg font-semibold leading-snug">{detail.title}</h2>
      <p className="mt-1 text-sm text-[var(--muted)]">{detail.authors}</p>
      {detail.venue && <p className="mt-0.5 text-sm italic text-[var(--muted)]">{detail.venue}</p>}
      <div className="mt-2 flex flex-wrap gap-3 text-xs text-[var(--muted)]">
        {detail.year && <span>Year: {detail.year}</span>}
        {detail.citation_count != null && <span>Citations: {detail.citation_count.toLocaleString()}</span>}
        {detail.doi && (
          <a className="text-[var(--primary)] hover:underline" href={`https://doi.org/${detail.doi}`} target="_blank" rel="noreferrer">
            DOI: {detail.doi}
          </a>
        )}
        {detail.url && (
          <a className="text-[var(--primary)] hover:underline" href={detail.url} target="_blank" rel="noreferrer">
            Open ↗
          </a>
        )}
      </div>
      <div className="mt-4">
        <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-[var(--muted)]">Abstract</div>
        <p className="text-sm leading-relaxed">{detail.abstract || "No abstract available."}</p>
      </div>
      {(detail.tags || detail.notes) && (
        <div className="mt-4 grid grid-cols-2 gap-4 text-sm">
          <div>
            <div className="text-xs font-semibold uppercase tracking-wide text-[var(--muted)]">Tags</div>
            <div>{detail.tags || "—"}</div>
          </div>
          <div>
            <div className="text-xs font-semibold uppercase tracking-wide text-[var(--muted)]">Notes</div>
            <div className="whitespace-pre-wrap">{detail.notes || "—"}</div>
          </div>
        </div>
      )}
    </div>
  );
}

function EditForm({
  draft,
  setDraft,
  onSave,
}: {
  draft: Partial<Article>;
  setDraft: (d: Partial<Article>) => void;
  onSave: () => void;
}) {
  const field = (key: keyof Article, label: string, textarea = false) => (
    <label className="block">
      <span className="mb-1 block text-xs font-semibold uppercase tracking-wide text-[var(--muted)]">{label}</span>
      {textarea ? (
        <textarea
          className="input min-h-24"
          value={(draft[key] as string) ?? ""}
          onChange={(e) => setDraft({ ...draft, [key]: e.target.value })}
        />
      ) : (
        <input
          className="input"
          value={(draft[key] as string | number) ?? ""}
          onChange={(e) => setDraft({ ...draft, [key]: e.target.value })}
        />
      )}
    </label>
  );
  return (
    <div className="space-y-3">
      {field("title", "Title")}
      {field("authors", "Authors")}
      <div className="grid grid-cols-2 gap-3">
        {field("year", "Year")}
        {field("pub_type", "Type")}
      </div>
      {field("doi", "DOI")}
      {field("url", "URL")}
      {field("abstract", "Abstract", true)}
      {field("tags", "Tags")}
      {field("notes", "Notes", true)}
      <div className="flex justify-end">
        <button className="btn btn-primary" onClick={onSave}>
          Save changes
        </button>
      </div>
    </div>
  );
}

function DecisionBadge({ value }: { value: string }) {
  const v = value || "unscreened";
  const cls = v === "include" ? "badge-include" : v === "maybe" ? "badge-maybe" : v === "exclude" ? "badge-exclude" : "";
  return <span className={`badge ${cls}`}>{v}</span>;
}

function DecisionDot({ value }: { value: string }) {
  const v = value || "unscreened";
  const color = v === "include" ? "#16a34a" : v === "maybe" ? "#d97706" : v === "exclude" ? "#dc2626" : "#98a2b3";
  return <span className="inline-block h-2 w-2 rounded-full" style={{ background: color }} title={v} />;
}
