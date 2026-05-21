"use client";

import { useEffect, useRef, useState } from "react";
import {
  collectRefs,
  findActiveCapture,
  getCaptureStatus,
  getInsights,
  startCapture,
  type AnalysisResult,
  type CaptureStatus,
  type Insights,
  type MissingRef,
} from "@/lib/api";

const PHASES: Record<string, string> = {
  "linking citations": "Linking citations",
  "finding gaps": "Finding gaps",
  "resolving missing": "Resolving missing papers",
  starting: "Starting",
  done: "Done",
};

export default function Analysis({
  projectId,
  onChanged,
  onOpenPaper,
}: {
  projectId: number;
  onChanged?: () => void;
  onOpenPaper?: (id: number) => void;
}) {
  const [insights, setInsights] = useState<Insights | null>(null);

  // ── Gap detection (manual) ───────────────────────────────────────────
  const [job, setJob] = useState<string | null>(null);
  const [status, setStatus] = useState<CaptureStatus | null>(null);
  const [analysis, setAnalysis] = useState<AnalysisResult | null>(null);
  const [collecting, setCollecting] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [err, setErr] = useState<string | null>(null);
  const poll = useRef<ReturnType<typeof setInterval> | null>(null);

  // Corpus analytics are local + fast — load them on open.
  useEffect(() => {
    getInsights(projectId).then(setInsights).catch(() => {});
  }, [projectId]);

  // Re-attach to a gap run already going (e.g. one you started then left), or
  // show its last finished result. Never auto-starts — only the button does.
  useEffect(() => {
    findActiveCapture(projectId).then((r) => {
      if (r.job_id) setJob(r.job_id);
      else if (r.latest_result) setAnalysis(r.latest_result);
    });
  }, [projectId]);

  useEffect(() => {
    if (!job) return;
    const tick = async () => {
      try {
        const s = await getCaptureStatus(job);
        setStatus(s);
        if (s.done) {
          if (poll.current) clearInterval(poll.current);
          setJob(null);
          if (s.result) {
            setAnalysis(s.result);
            onChanged?.();
          }
          if (s.error) setErr(s.error);
        }
      } catch {
        if (poll.current) clearInterval(poll.current);
        setJob(null);
      }
    };
    tick();
    poll.current = setInterval(tick, 1500);
    return () => {
      if (poll.current) clearInterval(poll.current);
    };
  }, [job, onChanged]);

  const findMissing = async () => {
    setErr(null);
    setAnalysis(null);
    try {
      const r = await startCapture(projectId);
      setJob(r.job_id);
    } catch (e) {
      setErr(String(e));
    }
  };

  const collect = async (items: MissingRef[]) => {
    if (items.length === 0) return;
    setCollecting(true);
    try {
      await collectRefs(projectId, items);
      const keys = new Set(items.map((i) => i.key));
      setAnalysis((a) =>
        a ? { ...a, missing: a.missing.filter((m) => !keys.has(m.key)), missing_count: a.missing_count - items.length } : a,
      );
      setSelected(new Set());
      onChanged?.();
    } finally {
      setCollecting(false);
    }
  };

  const toggle = (k: string) =>
    setSelected((s) => {
      const n = new Set(s);
      if (n.has(k)) n.delete(k);
      else n.add(k);
      return n;
    });

  const running = !!job;

  return (
    <div className="space-y-8">
      {/* ── Corpus overview ─────────────────────────────────────────── */}
      {insights && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Metric label="Papers in library" value={insights.total} />
          <Metric
            label="Year span"
            text={insights.year_min && insights.year_max ? `${insights.year_min}–${insights.year_max}` : "—"}
          />
          <Metric label="With reference lists" value={insights.papers_with_refs} />
          <Metric label="Added via references" value={insights.from_reference} good={insights.from_reference > 0} />
        </div>
      )}

      {/* ── Research landscape ──────────────────────────────────────── */}
      {insights && (
        <Section title="Research landscape" subtitle="Who, where, and when — at a glance, from your corpus.">
          <div className="grid gap-4 lg:grid-cols-2">
            <Card title="Publications per year">
              <YearTrend points={insights.by_year} />
            </Card>
            <Card title="Search saturation" subtitle="cumulative papers as the corpus grows">
              <Saturation points={insights.by_year} />
            </Card>
            <Card title="Top authors">
              <BarList items={insights.top_authors} />
            </Card>
            <Card title="Top venues">
              <BarList items={insights.top_venues} />
            </Card>
          </div>
        </Section>
      )}

      {/* ── Foundational core ───────────────────────────────────────── */}
      {insights && insights.foundational.length > 0 && (
        <Section
          title="Foundational core"
          subtitle="The papers cited most often by the other papers in your collection — the recurring references your set keeps pointing back to. (These are collected papers, not ones you wrote.)"
        >
          <div className="card overflow-hidden">
            {insights.foundational.map((f, i) => (
              <button
                key={f.id}
                onClick={() => onOpenPaper?.(f.id)}
                className="flex w-full items-center gap-3 border-b px-4 py-2.5 text-left text-sm last:border-0 hover:bg-[var(--surface-2)]"
              >
                <span className="w-5 shrink-0 text-right tabular-nums text-xs text-[var(--muted)]">{i + 1}</span>
                <div className="min-w-0 flex-1">
                  <div className="line-clamp-1 font-medium">{f.title}</div>
                  <div className="mt-0.5 flex items-center gap-2 text-xs text-[var(--muted)]">
                    <span>{f.year ?? "—"}</span>
                    {f.venue && <span className="line-clamp-1 italic">· {f.venue}</span>}
                    {typeof f.citation_count === "number" && <span>· {f.citation_count.toLocaleString()} global cites</span>}
                  </div>
                </div>
                <span
                  className="shrink-0 rounded-full bg-[#e0e7ff] px-2 py-0.5 text-[10px] font-semibold text-[#3730a3]"
                  title="Number of papers in your collection that cite this one"
                >
                  cited by {f.internal_cited_by} in your set
                </span>
              </button>
            ))}
          </div>
        </Section>
      )}

      {/* ── Find missing papers (gap detection — manual) ────────────── */}
      <Section
        title="Find missing papers"
        subtitle="Looks at what your collected papers cite, matches it against your library, and surfaces the works your set cites most that you don't have yet — ranked by how many of your papers cite them. Papers already collected in another project are copied in automatically. Runs only when you press the button."
      >
        <div className="card p-4">
          {!running ? (
            <button className="btn btn-primary" onClick={findMissing}>
              Find missing papers
            </button>
          ) : (
            <div>
              <div className="mb-1 flex justify-between text-sm">
                <span>Finding missing papers — {PHASES[status?.phase ?? ""] ?? "starting"}…</span>
                <span className="tabular-nums text-[var(--muted)]">{overallPct(status)}%</span>
              </div>
              <div className="h-2 overflow-hidden rounded-full bg-[var(--bg)]">
                <div
                  className="h-full rounded-full bg-[var(--primary)] transition-all"
                  style={{ width: `${overallPct(status)}%` }}
                />
              </div>
              {status && status.no_doi > 0 && (
                <div className="mt-1 text-xs text-[var(--muted)]">{status.no_doi} papers have no DOI — skipped</div>
              )}
            </div>
          )}
          {err && <div className="mt-2 text-xs text-[#b91c1c]">{err}</div>}
        </div>

        {analysis && (
          <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Metric label="Papers analyzed" value={analysis.papers_analyzed} />
            <Metric label="Unique references" value={analysis.unique_references} />
            <Metric label="Copied from other projects" value={analysis.copied_from_other_projects} good />
            <Metric label="Missing papers" value={analysis.missing_count} warn />
          </div>
        )}

        {analysis && analysis.missing.length > 0 && (
          <div className="card mt-3 overflow-hidden">
            <div className="flex flex-wrap items-center justify-between gap-2 border-b px-4 py-2.5">
              <div className="text-xs font-semibold uppercase tracking-wide text-[var(--muted)]">
                Missing papers — cited by your set, not collected
                {analysis.missing_total && analysis.missing_total > analysis.missing.length
                  ? ` (showing top ${analysis.missing.length} of ${analysis.missing_total.toLocaleString()})`
                  : ` (${analysis.missing.length})`}
              </div>
              <div className="flex items-center gap-2">
                <button
                  className="btn px-2 py-1 text-xs"
                  disabled={collecting || selected.size === 0}
                  onClick={() => collect(analysis.missing.filter((m) => selected.has(m.key)))}
                >
                  {collecting ? "Collecting…" : `Collect selected (${selected.size})`}
                </button>
                <button className="btn btn-primary px-2 py-1 text-xs" disabled={collecting} onClick={() => collect(analysis.missing)}>
                  Collect all
                </button>
              </div>
            </div>
            <div className="max-h-[26rem] overflow-y-auto">
              {analysis.missing.map((m) => (
                <div key={m.key} className="flex items-center gap-3 border-b px-4 py-2.5 text-sm last:border-0 hover:bg-[var(--surface-2)]">
                  <input type="checkbox" checked={selected.has(m.key)} onChange={() => toggle(m.key)} />
                  <div className="min-w-0 flex-1">
                    <div className="line-clamp-1 font-medium">{m.title}</div>
                    <div className="mt-0.5 flex items-center gap-2 text-xs text-[var(--muted)]">
                      <span>{m.year ?? "—"}</span>
                      {m.venue && <span className="line-clamp-1 italic">· {m.venue}</span>}
                      {m.doi && <span>· {m.doi}</span>}
                    </div>
                  </div>
                  <span className="shrink-0 rounded-full bg-[#fef3c7] px-2 py-0.5 text-[10px] font-semibold text-[#92400e]">
                    cited by {m.cited_by}
                  </span>
                  <button className="btn shrink-0 px-2 py-1 text-xs" disabled={collecting} onClick={() => collect([m])}>
                    Collect
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}

        {analysis && analysis.missing.length === 0 && (
          <div className="card mt-3 p-6 text-center text-sm text-[var(--muted)]">
            No missing papers — every work your set cites is already in your library (or was copied in).
          </div>
        )}
      </Section>
    </div>
  );
}

function overallPct(s: CaptureStatus | null): number {
  if (!s) return 5;
  if (s.done) return 100;
  const frac = s.total ? s.completed / s.total : 0;
  if (s.phase === "linking citations") return Math.min(55, Math.round(frac * 55));
  if (s.phase === "finding gaps") return 60;
  if (s.phase === "resolving missing") return Math.min(99, 60 + Math.round(frac * 39));
  return 8;
}

// ── Small presentational helpers ────────────────────────────────────────

function Section({ title, subtitle, children }: { title: string; subtitle?: string; children: React.ReactNode }) {
  return (
    <section>
      <h2 className="text-base font-semibold">{title}</h2>
      {subtitle && <p className="mb-3 mt-0.5 max-w-3xl text-sm text-[var(--muted)]">{subtitle}</p>}
      {children}
    </section>
  );
}

function Card({ title, subtitle, children }: { title: string; subtitle?: string; children: React.ReactNode }) {
  return (
    <div className="card p-4">
      <div className="mb-3">
        <div className="text-xs font-semibold uppercase tracking-wide text-[var(--muted)]">{title}</div>
        {subtitle && <div className="text-[10px] text-[var(--muted)]">{subtitle}</div>}
      </div>
      {children}
    </div>
  );
}

function Metric({ label, value, text, good, warn }: { label: string; value?: number; text?: string; good?: boolean; warn?: boolean }) {
  return (
    <div className="card p-3">
      <div className="text-lg font-semibold" style={{ color: good ? "#16a34a" : warn ? "#b45309" : "var(--text)" }}>
        {text ?? (value ?? 0).toLocaleString()}
      </div>
      <div className="text-[10px] uppercase tracking-wide text-[var(--muted)]">{label}</div>
    </div>
  );
}

function BarList({ items }: { items: { name: string; count: number }[] }) {
  if (items.length === 0) return <div className="text-xs italic text-[var(--muted)]">No data.</div>;
  const max = Math.max(...items.map((i) => i.count), 1);
  return (
    <div className="space-y-1.5">
      {items.map((it) => (
        <div key={it.name} className="flex items-center gap-2 text-xs">
          <div className="line-clamp-1 w-40 shrink-0 text-[var(--text)]" title={it.name}>
            {it.name}
          </div>
          <div className="h-3 flex-1 overflow-hidden rounded-sm bg-[var(--bg)]">
            <div className="h-full rounded-sm bg-[var(--primary)]" style={{ width: `${(it.count / max) * 100}%` }} />
          </div>
          <div className="w-8 shrink-0 text-right tabular-nums text-[var(--muted)]">{it.count}</div>
        </div>
      ))}
    </div>
  );
}

function YearTrend({ points }: { points: { year: number; count: number }[] }) {
  const [hover, setHover] = useState<number | null>(null);
  if (points.length === 0) return <div className="text-xs italic text-[var(--muted)]">No year data.</div>;
  const max = Math.max(...points.map((p) => p.count), 1);
  const h = hover != null ? points[hover] : null;
  return (
    <div>
      <div className="mb-1 h-4 text-xs text-[var(--muted)]">
        {h ? (
          <span>
            <b className="text-[var(--text)] tabular-nums">{h.year}</b> · {h.count.toLocaleString()} paper{h.count === 1 ? "" : "s"}
          </span>
        ) : (
          <span>Peak: {max.toLocaleString()} in one year · hover a bar</span>
        )}
      </div>
      {/* Bars are direct children of a definite-height flex row, so the % height
          resolves correctly (the earlier nested wrapper collapsed to 0). */}
      <div className="flex h-32 items-end gap-px">
        {points.map((p, i) => (
          <div
            key={p.year}
            onMouseEnter={() => setHover(i)}
            onMouseLeave={() => setHover(null)}
            title={`${p.year}: ${p.count}`}
            className="flex-1 rounded-t-sm bg-[var(--primary)] transition-opacity"
            style={{ height: `${Math.max((p.count / max) * 100, 2)}%`, opacity: hover == null || hover === i ? 1 : 0.4 }}
          />
        ))}
      </div>
      <div className="mt-1 flex justify-between text-[10px] text-[var(--muted)]">
        <span>{points[0].year}</span>
        <span>{points[points.length - 1].year}</span>
      </div>
    </div>
  );
}

function Saturation({ points }: { points: { year: number; cumulative: number }[] }) {
  const [hover, setHover] = useState<number | null>(null);
  if (points.length < 2) return <div className="text-xs italic text-[var(--muted)]">Not enough years to plot.</div>;
  const W = 100;
  const H = 40;
  const total = points[points.length - 1].cumulative || 1;
  const minY = points[0].year;
  const spanY = Math.max(points[points.length - 1].year - minY, 1);
  const xy = points.map((p) => ({ x: ((p.year - minY) / spanY) * W, y: H - (p.cumulative / total) * H }));
  const line = xy.map((c) => `${c.x.toFixed(2)},${c.y.toFixed(2)}`).join(" ");
  const area = `0,${H} ${line} ${W},${H}`;
  const h = hover != null ? points[hover] : null;
  return (
    <div>
      <div className="mb-1 h-4 text-xs text-[var(--muted)]">
        {h ? (
          <span>
            By <b className="text-[var(--text)] tabular-nums">{h.year}</b> · {h.cumulative.toLocaleString()} papers collected
          </span>
        ) : (
          <span>{total.toLocaleString()} papers total · hover to inspect</span>
        )}
      </div>
      <div className="relative h-32">
        <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" className="absolute inset-0 h-full w-full">
          <polygon points={area} fill="var(--primary)" opacity={0.12} />
          <polyline points={line} fill="none" stroke="var(--primary)" strokeWidth={1.5} vectorEffect="non-scaling-stroke" />
          {hover != null && (
            <line
              x1={xy[hover].x}
              y1={0}
              x2={xy[hover].x}
              y2={H}
              stroke="var(--muted)"
              strokeWidth={0.5}
              strokeDasharray="2"
              vectorEffect="non-scaling-stroke"
            />
          )}
        </svg>
        {/* Invisible hover columns drive the readout + marker. */}
        <div className="absolute inset-0 flex">
          {points.map((p, i) => (
            <div key={p.year} className="flex-1" onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)} />
          ))}
        </div>
        {hover != null && (
          <div
            className="pointer-events-none absolute h-2 w-2 -translate-x-1/2 -translate-y-1/2 rounded-full border border-white bg-[var(--primary)]"
            style={{ left: `${xy[hover].x}%`, top: `${(xy[hover].y / H) * 100}%` }}
          />
        )}
      </div>
      <div className="mt-1 flex justify-between text-[10px] text-[var(--muted)]">
        <span>{points[0].year}</span>
        <span>{points[points.length - 1].year}</span>
      </div>
    </div>
  );
}
