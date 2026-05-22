"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  cancelSearch,
  findActiveSearch,
  getSearchStatus,
  startSearch,
  suggestKeywords,
  type SearchStatus,
} from "@/lib/api";
import { Search as SearchIcon, ChevronRight, ChevronDown, X, Sparkles } from "lucide-react";
import { parseTerms } from "@/lib/parseTerms";

const TYPES = [
  ["both", "Review + research"],
  ["review", "Reviews"],
  ["research", "Research"],
] as const;

const SOURCES = [
  ["openalex", "OpenAlex"],
  ["pubmed", "PubMed"],
  ["s2", "Semantic Scholar"],
  ["arxiv", "arXiv"],
] as const;

export default function SearchPanel({
  projectId,
  defaultType = "both",
  topic = "",
  onViewLibrary,
}: {
  projectId: number;
  defaultType?: string;
  topic?: string;
  onViewLibrary?: () => void;
}) {
  const [queries, setQueries] = useState("");
  const [type, setType] = useState(defaultType);
  const [yearFrom, setYearFrom] = useState("");
  const [yearTo, setYearTo] = useState("");
  const [advanced, setAdvanced] = useState(false);
  const [sources, setSources] = useState<string[]>(["openalex", "pubmed", "s2", "arxiv"]);
  const [maxPerSource, setMaxPerSource] = useState(100);
  const [titleKeyword, setTitleKeyword] = useState("");
  const [matchMode, setMatchMode] = useState("any");

  const [jobId, setJobId] = useState<string | null>(null);
  const [status, setStatus] = useState<SearchStatus | null>(null);
  const [cancelling, setCancelling] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const terms = parseTerms(queries);
  const removeTerm = (idx: number) =>
    setQueries(terms.filter((_, i) => i !== idx).join("\n"));

  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [suggesting, setSuggesting] = useState(false);
  const [suggestNote, setSuggestNote] = useState<string | null>(null);

  const fetchSuggestions = async () => {
    setSuggesting(true);
    setSuggestNote(null);
    try {
      const r = await suggestKeywords(topic, terms);
      const fresh = r.terms.filter((t) => !terms.some((x) => x.toLowerCase() === t.toLowerCase()));
      setSuggestions(fresh);
      if (fresh.length === 0) {
        setSuggestNote(r.unavailable ? "AI suggestions unavailable (no API key)." : "No new suggestions.");
      }
    } catch {
      setSuggestNote("Couldn't reach the suggestion service.");
    } finally {
      setSuggesting(false);
    }
  };

  const addSuggestion = (t: string) => {
    setQueries((q) => (q.trim() ? `${q}\n${t}` : t));
    setSuggestions((s) => s.filter((x) => x !== t));
  };
  const poll = useRef<ReturnType<typeof setInterval> | null>(null);

  // Re-attach to a running search after a refresh.
  useEffect(() => {
    findActiveSearch(projectId, type).then((r) => {
      if (r.job_id) setJobId(r.job_id);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  const stopPolling = useCallback(() => {
    if (poll.current) clearInterval(poll.current);
    poll.current = null;
  }, []);

  useEffect(() => {
    if (!jobId) return;
    const tick = async () => {
      try {
        const s = await getSearchStatus(jobId);
        setStatus(s);
        if (s.done) {
          stopPolling();
          setJobId(null);
          setCancelling(false);
        }
      } catch {
        stopPolling();
        setJobId(null);
      }
    };
    tick();
    poll.current = setInterval(tick, 1500);
    return stopPolling;
  }, [jobId, stopPolling]);

  const toggleSource = (s: string) =>
    setSources((cur) => (cur.includes(s) ? cur.filter((x) => x !== s) : [...cur, s]));

  const run = async () => {
    const qs = parseTerms(queries);
    if (qs.length === 0) {
      setErr("Enter at least one search term.");
      return;
    }
    if (sources.length === 0) {
      setErr("Select at least one source.");
      return;
    }
    setErr(null);
    setStatus(null);
    try {
      const r = await startSearch(projectId, {
        queries: qs,
        type,
        year_from: yearFrom ? Number(yearFrom) : null,
        year_to: yearTo ? Number(yearTo) : null,
        sources,
        max_per_source: maxPerSource,
        title_keyword: titleKeyword,
        match_mode: matchMode,
      });
      setJobId(r.job_id);
    } catch (e) {
      setErr(String(e));
    }
  };

  const running = !!jobId;

  // Derive a single high-level phase for the Progress chip from the status file.
  // Cancellation isn't a dedicated field, so we detect it from the log line the
  // worker writes ("Cancelled by user …").
  const cancelled = !!status && status.log.some((l) => l.toLowerCase().includes("cancelled by user"));
  const phase: "running" | "done" | "cancelled" | "error" = status?.error
    ? "error"
    : cancelled
    ? "cancelled"
    : status?.done
    ? "done"
    : "running";
  const sourceWarnings = status ? status.log.filter((l) => l.includes("source warning")).length : 0;

  return (
    <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
      {/* Form */}
      <div className="card p-5">
        <label className="mb-1 block text-xs font-medium text-[var(--muted)]">
          Search terms <span className="font-normal">(one per line or comma-separated — each runs across all sources)</span>
        </label>
        <textarea
          className="input min-h-[120px] w-full font-mono text-sm"
          placeholder={"liposomal drug delivery\npH-responsive nanoparticle\n…"}
          value={queries}
          onChange={(e) => setQueries(e.target.value)}
          disabled={running}
        />
        {terms.length > 0 && (
          <div className="mt-2 flex flex-wrap items-center gap-1.5">
            <span className="text-xs text-[var(--muted)]">
              {terms.length} term{terms.length === 1 ? "" : "s"}:
            </span>
            {terms.map((t, i) => (
              <span
                key={`${t}-${i}`}
                className="inline-flex items-center gap-1 rounded-full border border-[var(--border)] bg-[var(--surface-2)] px-2 py-0.5 text-xs"
              >
                {t}
                {!running && (
                  <button
                    type="button"
                    onClick={() => removeTerm(i)}
                    className="text-[var(--muted)] hover:text-[var(--danger)]"
                    aria-label={`Remove ${t}`}
                  >
                    <X size={11} />
                  </button>
                )}
              </span>
            ))}
          </div>
        )}

        <div className="mt-2">
          <div className="flex items-center gap-2">
            <button
              type="button"
              className="flex items-center gap-1 text-xs font-medium text-[var(--primary)] hover:underline disabled:opacity-50"
              onClick={fetchSuggestions}
              disabled={suggesting || running}
            >
              <Sparkles size={12} /> {suggesting ? "Thinking…" : "Suggest terms"}
            </button>
            {suggestNote && <span className="text-xs text-[var(--muted)]">{suggestNote}</span>}
          </div>
          {suggestions.length > 0 && (
            <div className="mt-1.5 flex flex-wrap gap-1.5">
              {suggestions.map((t) => (
                <button
                  key={t}
                  type="button"
                  onClick={() => addSuggestion(t)}
                  className="rounded-full border border-dashed border-[var(--primary)] px-2 py-0.5 text-xs text-[var(--primary)] hover:bg-[var(--primary-weak)]"
                >
                  + {t}
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="mt-4 flex flex-wrap items-end gap-4">
          <div>
            <label className="mb-1 block text-xs font-medium text-[var(--muted)]">Type</label>
            <div className="flex gap-1.5">
              {TYPES.map(([val, label]) => (
                <button
                  key={val}
                  type="button"
                  disabled={running}
                  onClick={() => setType(val)}
                  className={`rounded-md border px-3 py-1.5 text-xs font-medium transition ${
                    type === val
                      ? "border-[var(--primary)] bg-[var(--primary)] text-white"
                      : "border-[var(--border)] text-[var(--muted)] hover:text-[var(--text)]"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-[var(--muted)]">Year range</label>
            <div className="flex items-center gap-1.5">
              <input
                className="input w-20"
                placeholder="from"
                value={yearFrom}
                inputMode="numeric"
                onChange={(e) => setYearFrom(e.target.value.replace(/\D/g, ""))}
                disabled={running}
              />
              <span className="text-[var(--muted)]">–</span>
              <input
                className="input w-20"
                placeholder="to"
                value={yearTo}
                inputMode="numeric"
                onChange={(e) => setYearTo(e.target.value.replace(/\D/g, ""))}
                disabled={running}
              />
            </div>
          </div>
        </div>

        <button
          type="button"
          className="mt-4 flex items-center gap-1 text-xs font-medium text-[var(--muted)] hover:text-[var(--text)]"
          onClick={() => setAdvanced((a) => !a)}
        >
          {advanced ? <ChevronDown size={13} /> : <ChevronRight size={13} />} Advanced options
        </button>

        {advanced && (
          <div className="mt-3 space-y-3 rounded-md border border-[var(--border)] p-3">
            <div>
              <div className="mb-1 text-xs font-medium text-[var(--muted)]">Sources</div>
              <div className="flex flex-wrap gap-3">
                {SOURCES.map(([val, label]) => (
                  <label key={val} className="flex items-center gap-1.5 text-sm">
                    <input
                      type="checkbox"
                      checked={sources.includes(val)}
                      onChange={() => toggleSource(val)}
                      disabled={running}
                    />
                    {label}
                  </label>
                ))}
              </div>
            </div>
            <div className="flex flex-wrap items-end gap-4">
              <div>
                <label className="mb-1 block text-xs font-medium text-[var(--muted)]">
                  Max per source
                </label>
                <input
                  className="input w-24"
                  value={maxPerSource}
                  inputMode="numeric"
                  onChange={(e) => setMaxPerSource(Number(e.target.value.replace(/\D/g, "")) || 0)}
                  disabled={running}
                />
              </div>
              <div className="min-w-[200px] flex-1">
                <label className="mb-1 block text-xs font-medium text-[var(--muted)]">
                  Title must contain (optional)
                </label>
                <input
                  className="input w-full"
                  placeholder="comma-separated, e.g. amide, peptide"
                  value={titleKeyword}
                  onChange={(e) => setTitleKeyword(e.target.value)}
                  disabled={running}
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-[var(--muted)]">Match</label>
                <select
                  className="input w-24"
                  value={matchMode}
                  onChange={(e) => setMatchMode(e.target.value)}
                  disabled={running}
                >
                  <option value="any">any</option>
                  <option value="all">all</option>
                </select>
              </div>
            </div>
          </div>
        )}

        {err && <div className="mt-3 text-xs text-[var(--danger)]">{err}</div>}

        <div className="mt-4">
          {!running ? (
            <button className="btn btn-primary" onClick={run}>
              <SearchIcon size={15} /> Search &amp; collect
            </button>
          ) : (
            <button
              className="btn"
              disabled={cancelling}
              onClick={() => {
                if (!jobId) return;
                setCancelling(true);
                cancelSearch(jobId);
              }}
            >
              {cancelling ? "Cancelling…" : "Cancel"}
            </button>
          )}
        </div>
      </div>

      {/* Progress */}
      <div className="card p-5">
        <div className="text-xs font-semibold uppercase tracking-wide text-[var(--muted)]">
          Progress
        </div>
        {!status && (
          <p className="mt-3 text-sm text-[var(--muted)]">
            Results are added to your <b>Library</b> as each search completes. Duplicates are skipped
            automatically.
          </p>
        )}
        {status && (
          <div className="mt-3">
            <div className="mb-2 flex items-center justify-between gap-2">
              <PhaseChip phase={phase} />
              <span className="text-sm text-[var(--muted)]">
                <span className="tnum font-mono text-[var(--text)]">{status.completed}</span>
                <span className="text-[var(--muted)]">/{status.total}</span> searches
              </span>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-[var(--bg)]">
              <div
                className={`h-full rounded-full transition-all ${
                  phase === "error" ? "bg-[var(--danger)]" : phase === "cancelled" ? "bg-amber-500" : phase === "done" ? "bg-[var(--success)]" : "bg-[var(--primary)]"
                }`}
                style={{ width: `${status.total ? (status.completed / status.total) * 100 : 0}%` }}
              />
            </div>

            {/* Live tallies — always visible so the run's outcome is scannable. */}
            <div className="mt-3 flex flex-wrap gap-2">
              <StatChip label="Articles found" value={status.total_added} tone="#16a34a" />
              <StatChip label="Duplicates" value={status.duplicates_removed} tone="#0ea5e9" />
              <StatChip label="Filtered" value={status.total_skipped} tone="#64748b" />
              {sourceWarnings > 0 && <StatChip label="Source warnings" value={sourceWarnings} tone="#d97706" />}
            </div>

            {status.current_query && !status.done && (
              <div className="mt-2 line-clamp-1 text-xs text-[var(--muted)]">
                Now: {status.current_query}
              </div>
            )}
            {status.error && <div className="mt-2 text-xs text-[var(--danger)]">{status.error}</div>}
            {status.log.length > 0 && (
              <div className="mt-3 max-h-64 space-y-1 overflow-y-auto rounded-md bg-[var(--surface-2)] p-2 text-xs">
                {status.log.slice(-80).map((line, i) => (
                  <div key={i} className="text-[var(--muted)]">
                    {line}
                  </div>
                ))}
              </div>
            )}
            {status.done && status.total_added > 0 && onViewLibrary && (
              <button className="btn btn-primary mt-3" onClick={onViewLibrary}>
                View {status.total_added} papers in Library →
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function PhaseChip({ phase }: { phase: "running" | "done" | "cancelled" | "error" }) {
  const cfg = {
    running: { label: "In progress", color: "#2563eb", bg: "#2563eb1a", pulse: true },
    done: { label: "Completed", color: "#16a34a", bg: "#16a34a1a", pulse: false },
    cancelled: { label: "Cancelled", color: "#d97706", bg: "#d977061a", pulse: false },
    error: { label: "Error", color: "#dc2626", bg: "#dc26261a", pulse: false },
  }[phase];
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold"
      style={{ color: cfg.color, background: cfg.bg }}
    >
      <span
        className={`h-2 w-2 rounded-full ${cfg.pulse ? "animate-pulse" : ""}`}
        style={{ background: cfg.color }}
      />
      {cfg.label}
    </span>
  );
}

function StatChip({ label, value, tone }: { label: string; value: number; tone: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-[var(--border)] bg-[var(--surface)] px-2.5 py-1 text-xs">
      <span className="h-2 w-2 rounded-full" style={{ background: tone }} />
      <span className="text-[var(--muted)]">{label}</span>
      <span className="tnum font-mono font-semibold text-[var(--text)]">{(value ?? 0).toLocaleString()}</span>
    </span>
  );
}
