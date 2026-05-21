"use client";

import { useCallback, useEffect, useState } from "react";
import { collectAllReferences, collectReference, getArticleReferences } from "@/lib/api";
import type { ReferencePanel } from "@/lib/types";

// Companion panel shown beside the paper modal: lists the paper's fetched
// references and lets you pull them into the Library (one, or all collectable).
export default function ReferencesPanel({
  articleId,
  reloadToken = 0,
  onChanged,
  onOpenArticle,
}: {
  articleId: number;
  reloadToken?: number;
  onChanged?: () => void;
  onOpenArticle?: (id: number) => void;
}) {
  const [data, setData] = useState<ReferencePanel | null>(null);
  const [busyAll, setBusyAll] = useState(false);
  const [busyDoi, setBusyDoi] = useState<string | null>(null);

  const load = useCallback(() => {
    getArticleReferences(articleId).then(setData).catch(() => setData(null));
  }, [articleId]);

  useEffect(() => {
    setData(null);
    load();
    // reloadToken changes when the modal (re)fetches this paper's references.
  }, [load, reloadToken]);

  const collectOne = async (doi: string) => {
    setBusyDoi(doi);
    try {
      await collectReference(articleId, doi);
      load();
      onChanged?.();
    } finally {
      setBusyDoi(null);
    }
  };

  const collectAll = async () => {
    setBusyAll(true);
    try {
      await collectAllReferences(articleId);
      load();
      onChanged?.();
    } finally {
      setBusyAll(false);
    }
  };

  if (!data) {
    return (
      <div className="card hidden max-h-[90vh] w-80 shrink-0 self-center overflow-hidden p-4 shadow-2xl lg:block">
        <div className="h-5 w-1/2 animate-pulse rounded bg-[var(--bg)]" />
        <div className="mt-3 h-40 animate-pulse rounded bg-[var(--bg)]" />
      </div>
    );
  }

  const allDone = data.collectable === 0 && data.total - data.no_doi > 0;

  return (
    <div className="card hidden max-h-[90vh] w-80 shrink-0 flex-col self-center overflow-hidden p-0 shadow-2xl lg:flex">
      <div className="flex items-center justify-between gap-2 border-b px-4 py-3">
        <div>
          <div className="text-sm font-semibold">References ({data.total})</div>
          <div className="mt-0.5 text-[11px] text-[var(--muted)]">
            {data.in_library} in library · {data.collectable} to collect
            {data.no_doi > 0 && <> · {data.no_doi} no DOI</>}
          </div>
        </div>
        <button
          className="btn btn-primary shrink-0 px-2 py-1 text-xs disabled:opacity-40"
          onClick={collectAll}
          disabled={busyAll || data.collectable === 0}
          title="Resolve and add every reference that has a DOI"
        >
          {busyAll ? "Collecting…" : allDone ? "All collected" : `Collect all (${data.collectable})`}
        </button>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        {data.references.length === 0 && (
          <div className="p-4 text-xs italic text-[var(--muted)]">No references fetched for this paper yet.</div>
        )}
        {data.references.map((r, i) => (
          <div key={i} className="border-b px-4 py-2.5 text-xs last:border-0">
            <div className="font-medium leading-snug">{r.title}</div>
            <div className="mt-1 flex items-center justify-between gap-2">
              <span className="text-[var(--muted)]">
                {r.year ?? "—"}
                {r.venue && <span className="italic"> · {r.venue}</span>}
              </span>
              {r.status === "in_library" ? (
                <button
                  className="shrink-0 rounded-full bg-[#dcfce7] px-2 py-0.5 text-[10px] font-semibold text-[#166534] enabled:hover:bg-[#bbf7d0] disabled:cursor-default"
                  onClick={() => r.library_id != null && onOpenArticle?.(r.library_id)}
                  disabled={!onOpenArticle || r.library_id == null}
                  title="Open this reference in the Library"
                >
                  ✓ In library
                </button>
              ) : r.status === "collectable" ? (
                <button
                  className="btn shrink-0 px-2 py-0.5 text-[10px] disabled:opacity-40"
                  onClick={() => collectOne(r.doi)}
                  disabled={busyDoi === r.doi || busyAll}
                >
                  {busyDoi === r.doi ? "…" : "Collect"}
                </button>
              ) : (
                <span className="shrink-0 text-[10px] italic text-[var(--muted)]" title="No DOI — can't resolve">
                  no DOI
                </span>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
