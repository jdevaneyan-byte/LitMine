"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  cancelEnrich,
  findActiveEnrich,
  getCompleteness,
  getEnrichStatus,
  listIncomplete,
  startEnrich,
  type Completeness,
  type EnrichStatus,
  type IncompleteArticle,
} from "@/lib/api";

const FIELD_LABELS: Record<string, string> = {
  title: "Title",
  authors: "Authors",
  year: "Year",
  doi: "DOI",
  abstract: "Abstract",
  venue: "Journal",
};

export default function DataQuality({
  projectId,
  onFix,
}: {
  projectId: number;
  onFix?: (articleId: number) => void;
}) {
  const [report, setReport] = useState<Completeness | null>(null);
  const [incomplete, setIncomplete] = useState<IncompleteArticle[]>([]);
  const [jobId, setJobId] = useState<string | null>(null);
  const [status, setStatus] = useState<EnrichStatus | null>(null);
  const poll = useRef<ReturnType<typeof setInterval> | null>(null);

  const loadReport = useCallback(() => {
    getCompleteness(projectId).then(setReport).catch(() => setReport(null));
    listIncomplete(projectId).then((r) => setIncomplete(r.items)).catch(() => setIncomplete([]));
  }, [projectId]);

  useEffect(() => {
    loadReport();
    findActiveEnrich(projectId).then((r) => {
      if (r.job_id) setJobId(r.job_id);
    });
  }, [projectId, loadReport]);

  // Poll the running job.
  useEffect(() => {
    if (!jobId) return;
    const tick = async () => {
      try {
        const s = await getEnrichStatus(jobId);
        setStatus(s);
        if (s.done) {
          if (poll.current) clearInterval(poll.current);
          setJobId(null);
          loadReport();
        }
      } catch {
        if (poll.current) clearInterval(poll.current);
        setJobId(null);
      }
    };
    tick();
    poll.current = setInterval(tick, 1500);
    return () => {
      if (poll.current) clearInterval(poll.current);
    };
  }, [jobId, loadReport]);

  const run = async () => {
    setStatus(null);
    const r = await startEnrich(projectId);
    setJobId(r.job_id);
  };

  const pct = report && report.total ? Math.round((report.complete / report.total) * 100) : 0;

  return (
    <div className="space-y-4">
      <p className="text-sm text-[var(--muted)]">
        The data-quality worker checks every paper for missing core fields, then fills the gaps for
        papers that have a DOI by cascading across <b>Crossref → OpenAlex → Semantic Scholar</b> — only
        the empty fields are touched. Papers with no DOI are flagged for manual attention.
      </p>

      {report && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
          <Metric label="Total" value={report.total} />
          <Metric label="Complete" value={`${report.complete} (${pct}%)`} good />
          <Metric label="Incomplete" value={report.incomplete} />
          <Metric label="Fixable (has DOI)" value={report.fixable_with_doi} />
          <Metric label="No DOI — manual" value={report.incomplete_no_doi} warn />
        </div>
      )}

      {report && (
        <div className="card p-4">
          <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--muted)]">
            Missing by field
          </div>
          <div className="space-y-2">
            {Object.entries(report.missing_by_field).map(([f, n]) => {
              const frac = report.total ? n / report.total : 0;
              return (
                <div key={f} className="flex items-center gap-3 text-sm">
                  <span className="w-24 shrink-0">{FIELD_LABELS[f] ?? f}</span>
                  <div className="h-2 flex-1 overflow-hidden rounded-full bg-[var(--bg)]">
                    <div
                      className="h-full rounded-full"
                      style={{ width: `${frac * 100}%`, background: n ? "#f59e0b" : "#16a34a" }}
                    />
                  </div>
                  <span className="w-24 shrink-0 text-right tabular-nums text-[var(--muted)]">
                    {n} missing
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      <div className="flex items-center gap-3">
        {!jobId ? (
          <button
            className="btn btn-primary"
            onClick={run}
            disabled={!report || report.fixable_with_doi === 0}
          >
            Fill gaps from other sources
            {report ? ` (${report.fixable_with_doi})` : ""}
          </button>
        ) : (
          <button className="btn" onClick={() => cancelEnrich(jobId)}>
            Cancel
          </button>
        )}
        <button className="btn" onClick={loadReport}>
          Refresh audit
        </button>
      </div>

      {incomplete.length > 0 && (
        <div className="card overflow-hidden">
          <div className="flex items-center justify-between border-b px-4 py-2.5">
            <div className="text-xs font-semibold uppercase tracking-wide text-[var(--muted)]">
              Needs attention ({incomplete.length})
            </div>
            <div className="text-xs text-[var(--muted)]">
              Anything the worker couldn’t fill — open it in Read &amp; review to complete by hand.
            </div>
          </div>
          <div className="max-h-[28rem] overflow-y-auto">
            {incomplete.map((a) => (
              <div
                key={a.id}
                className="flex items-center gap-3 border-b px-4 py-2.5 text-sm last:border-0 hover:bg-[var(--surface-2)]"
              >
                <div className="min-w-0 flex-1">
                  <div className="line-clamp-1 font-medium">{a.title}</div>
                  <div className="mt-0.5 flex items-center gap-2 text-xs text-[var(--muted)]">
                    <span>{a.year ?? "—"}</span>
                    {a.venue && <span className="line-clamp-1 italic">· {a.venue}</span>}
                    {!a.has_doi && <span className="badge badge-exclude">no DOI</span>}
                  </div>
                </div>
                <div className="flex shrink-0 flex-wrap justify-end gap-1">
                  {a.missing.map((f) => (
                    <span
                      key={f}
                      className="rounded-full px-2 py-0.5 text-[10px] font-medium"
                      style={{ background: "#fef3c7", color: "#92400e" }}
                    >
                      {FIELD_LABELS[f] ?? f}
                    </span>
                  ))}
                </div>
                <button className="btn btn-primary shrink-0 px-3 py-1 text-xs" onClick={() => onFix?.(a.id)}>
                  Fix →
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {status && (
        <div className="card p-4">
          <div className="mb-1 flex items-center justify-between text-sm">
            <span>
              {status.done ? "Done" : "Working"} — {status.completed}/{status.total}
            </span>
            <span className="text-[var(--muted)]">
              {status.records_improved} papers improved · {status.filled_fields} fields filled
            </span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-[var(--bg)]">
            <div
              className="h-full rounded-full bg-[var(--primary)] transition-all"
              style={{ width: `${status.total ? (status.completed / status.total) * 100 : 0}%` }}
            />
          </div>
          {status.current && !status.done && (
            <div className="mt-2 line-clamp-1 text-xs text-[var(--muted)]">Now: {status.current}</div>
          )}
          {status.error && <div className="mt-2 text-xs text-[#b91c1c]">{status.error}</div>}
          {status.log.length > 0 && (
            <div className="mt-3 max-h-48 overflow-y-auto rounded-md bg-[var(--surface-2)] p-2 text-xs">
              {status.log.slice(-60).map((line, i) => (
                <div key={i} className="text-[var(--muted)]">
                  {line}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function Metric({ label, value, good, warn }: { label: string; value: number | string; good?: boolean; warn?: boolean }) {
  return (
    <div className="card p-3">
      <div
        className="text-lg font-semibold"
        style={{ color: good ? "#16a34a" : warn ? "#b45309" : "var(--text)" }}
      >
        {typeof value === "number" ? value.toLocaleString() : value}
      </div>
      <div className="text-[10px] uppercase tracking-wide text-[var(--muted)]">{label}</div>
    </div>
  );
}
