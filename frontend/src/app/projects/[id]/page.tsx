"use client";

import { use, useEffect, useState } from "react";
import Link from "next/link";
import { getProject, listArticles } from "@/lib/api";
import type { Article, Project } from "@/lib/types";
import ReadReview from "@/components/ReadReview";
import NetworkMap from "@/components/NetworkMap";
import Trash from "@/components/Trash";

const DECISIONS = ["all", "unscreened", "include", "maybe", "exclude"];
const PAGE = 50;

export default function ProjectPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const projectId = Number(id);

  const [project, setProject] = useState<Project | null>(null);
  const [tab, setTab] = useState<"library" | "read" | "network" | "trash">("library");

  useEffect(() => {
    getProject(projectId).then(setProject).catch(() => setProject(null));
  }, [projectId]);

  return (
    <div>
      <div className="mb-4 flex items-center gap-2 text-sm text-[var(--muted)]">
        <Link href="/" className="hover:text-[var(--text)]">
          Projects
        </Link>
        <span>/</span>
        <span className="text-[var(--text)]">{project?.name ?? "…"}</span>
      </div>

      <div className="mb-5 flex items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">{project?.name ?? "Loading…"}</h1>
          {project?.topic && (
            <p className="mt-1 text-sm text-[var(--muted)]">
              Topic: <code>{project.topic}</code> · {project.literature_type}
            </p>
          )}
        </div>
      </div>

      <div className="mb-5 flex gap-1 border-b">
        {([
          ["library", "Library"],
          ["read", "Read & review"],
          ["network", "Network map"],
          ["trash", "Trash"],
        ] as const).map(([key, label]) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={`-mb-px border-b-2 px-4 py-2 text-sm font-medium transition ${
              tab === key
                ? "border-[var(--primary)] text-[var(--primary)]"
                : "border-transparent text-[var(--muted)] hover:text-[var(--text)]"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === "library" && <LibraryTab projectId={projectId} />}
      {tab === "read" && <ReadReview projectId={projectId} />}
      {tab === "network" && <NetworkMap projectId={projectId} />}
      {tab === "trash" && <Trash projectId={projectId} />}
    </div>
  );
}

const CATEGORIES = [
  "all",
  "Review",
  "Research article",
  "Conference",
  "Book/Chapter",
  "Preprint",
  "Editorial/Note",
  "Dataset",
  "Unclassified",
];

function LibraryTab({ projectId }: { projectId: number }) {
  const [items, setItems] = useState<Article[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState("");
  const [decision, setDecision] = useState("all");
  const [category, setCategory] = useState("all");
  const [sort, setSort] = useState<"year" | "citations">("year");
  const [page, setPage] = useState(0);

  useEffect(() => {
    setLoading(true);
    const handle = setTimeout(() => {
      listArticles(projectId, { q, decision, category, sort, limit: PAGE, offset: page * PAGE })
        .then((r) => {
          setItems(r.items);
          setTotal(r.total);
        })
        .finally(() => setLoading(false));
    }, 250); // debounce the keyword box
    return () => clearTimeout(handle);
  }, [projectId, q, decision, category, sort, page]);

  const pages = Math.max(1, Math.ceil(total / PAGE));

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <input
          className="input max-w-xs"
          placeholder="Filter by title…"
          value={q}
          onChange={(e) => {
            setPage(0);
            setQ(e.target.value);
          }}
        />
        <select
          className="input max-w-[160px]"
          value={decision}
          onChange={(e) => {
            setPage(0);
            setDecision(e.target.value);
          }}
        >
          {DECISIONS.map((d) => (
            <option key={d} value={d}>
              {d === "all" ? "All decisions" : d}
            </option>
          ))}
        </select>
        <select
          className="input max-w-[180px]"
          value={category}
          onChange={(e) => {
            setPage(0);
            setCategory(e.target.value);
          }}
          title="Filter by publication type"
        >
          {CATEGORIES.map((c) => (
            <option key={c} value={c}>
              {c === "all" ? "All types" : c}
            </option>
          ))}
        </select>
        <select
          className="input max-w-[170px]"
          value={sort}
          onChange={(e) => {
            setPage(0);
            setSort(e.target.value as "year" | "citations");
          }}
          title="Sort order"
        >
          <option value="year">Sort: newest first</option>
          <option value="citations">Sort: most cited</option>
        </select>
        <span className="ml-auto text-xs text-[var(--muted)]">
          {total.toLocaleString()} papers
        </span>
      </div>

      <div className="card overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b bg-[var(--surface-2)] text-left text-xs uppercase tracking-wide text-[var(--muted)]">
              <th className="px-3 py-2 font-medium">#</th>
              <th className="px-3 py-2 font-medium">Title</th>
              <th className="px-3 py-2 font-medium">Year</th>
              <th className="px-3 py-2 text-right font-medium">Citations</th>
              <th className="px-3 py-2 font-medium">Type</th>
              <th className="px-3 py-2 font-medium">Source</th>
              <th className="px-3 py-2 font-medium">Decision</th>
            </tr>
          </thead>
          <tbody>
            {loading &&
              Array.from({ length: 8 }).map((_, i) => (
                <tr key={i} className="border-b">
                  <td colSpan={7} className="px-3 py-3">
                    <div className="h-4 animate-pulse rounded bg-[var(--bg)]" />
                  </td>
                </tr>
              ))}
            {!loading &&
              items.map((a, i) => (
                <tr key={a.id} className="border-b last:border-0 hover:bg-[var(--surface-2)]">
                  <td className="px-3 py-2 text-[var(--muted)]">{page * PAGE + i + 1}</td>
                  <td className="px-3 py-2">
                    <span className="line-clamp-2">{a.title}</span>
                    <span className="text-xs text-[var(--muted)]">{a.authors}</span>
                  </td>
                  <td className="px-3 py-2 tabular-nums">{a.year ?? ""}</td>
                  <td className="px-3 py-2 text-right tabular-nums">
                    {a.citation_count != null ? a.citation_count.toLocaleString() : <span className="text-[var(--muted)]">—</span>}
                  </td>
                  <td className="px-3 py-2 text-xs text-[var(--muted)]">{a.category || "Unclassified"}</td>
                  <td className="px-3 py-2 text-xs text-[var(--muted)]">{a.source}</td>
                  <td className="px-3 py-2">
                    <DecisionBadge value={a.screening_status} />
                  </td>
                </tr>
              ))}
            {!loading && items.length === 0 && (
              <tr>
                <td colSpan={7} className="px-3 py-8 text-center text-sm text-[var(--muted)]">
                  No matching papers.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="mt-3 flex items-center justify-between text-sm">
        <button className="btn" disabled={page === 0} onClick={() => setPage((p) => p - 1)}>
          ← Prev
        </button>
        <span className="text-[var(--muted)]">
          Page {page + 1} of {pages}
        </span>
        <button className="btn" disabled={page >= pages - 1} onClick={() => setPage((p) => p + 1)}>
          Next →
        </button>
      </div>
    </div>
  );
}

function DecisionBadge({ value }: { value: string }) {
  const v = value || "unscreened";
  const cls =
    v === "include" ? "badge-include" : v === "maybe" ? "badge-maybe" : v === "exclude" ? "badge-exclude" : "";
  return <span className={`badge ${cls}`}>{v}</span>;
}
