"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  cancelSearch,
  findActiveSearch,
  getSearchStatus,
  startSearch,
  type SearchStatus,
} from "@/lib/api";
import { Search as SearchIcon, ChevronRight, ChevronDown } from "lucide-react";

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
  onViewLibrary,
}: {
  projectId: number;
  defaultType?: string;
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
  const [err, setErr] = useState<string | null>(null);
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
    const qs = queries
      .split("\n")
      .map((q) => q.trim())
      .filter(Boolean);
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

  return (
    <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
      {/* Form */}
      <div className="card p-5">
        <label className="mb-1 block text-xs font-medium text-[var(--muted)]">
          Search terms <span className="font-normal">(one per line — each runs across all sources)</span>
        </label>
        <textarea
          className="input min-h-[120px] w-full font-mono text-sm"
          placeholder={"liposomal drug delivery\npH-responsive nanoparticle\n…"}
          value={queries}
          onChange={(e) => setQueries(e.target.value)}
          disabled={running}
        />

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
            <button className="btn" onClick={() => jobId && cancelSearch(jobId)}>
              Cancel
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
            <div className="mb-1 flex items-center justify-between text-sm">
              <span>
                {status.done ? "Done" : "Searching"} — <span className="tnum font-mono">{status.completed}/{status.total}</span>
              </span>
              <span className="text-[var(--muted)]">
                <span className="tnum font-mono text-[var(--success)]">{status.total_added}</span> added · <span className="tnum font-mono">{status.total_skipped}</span> filtered
              </span>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-[var(--bg)]">
              <div
                className="h-full rounded-full bg-[var(--primary)] transition-all"
                style={{ width: `${status.total ? (status.completed / status.total) * 100 : 0}%` }}
              />
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
            {status.done && status.duplicates_removed > 0 && (
              <div className="mt-2 text-xs text-[var(--muted)]">
                Removed <span className="tnum font-mono">{status.duplicates_removed}</span> fuzzy duplicate(s) after collecting.
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
