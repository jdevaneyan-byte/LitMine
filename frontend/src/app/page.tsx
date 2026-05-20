"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { listProjects } from "@/lib/api";
import type { ProjectSummary } from "@/lib/types";

export default function HomePage() {
  const [projects, setProjects] = useState<ProjectSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listProjects()
      .then(setProjects)
      .catch((e) => setError(String(e)));
  }, []);

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight">Projects</h1>
        <p className="mt-1 text-sm text-[var(--muted)]">
          Choose a project to read, review, and explore its citation network.
        </p>
      </div>

      {error && (
        <div className="card p-4 text-sm text-[#b91c1c]">
          Could not reach the API at <code>{process.env.NEXT_PUBLIC_API_BASE}</code>. Is the
          backend running?
          <br />
          <span className="text-[var(--muted)]">{error}</span>
        </div>
      )}

      {!projects && !error && <SkeletonGrid />}

      {projects && projects.length === 0 && (
        <div className="card p-8 text-center text-sm text-[var(--muted)]">
          No projects yet. Create one in the Streamlit app, then refresh.
        </div>
      )}

      {projects && projects.length > 0 && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {projects.map((p) => (
            <Link
              key={p.id}
              href={`/projects/${p.id}`}
              className="card block p-5 transition hover:shadow-md"
            >
              <div className="flex items-start justify-between gap-2">
                <h2 className="text-base font-semibold">{p.name}</h2>
                <span className="badge">{p.literature_type}</span>
              </div>
              <p className="mt-1 line-clamp-1 text-xs text-[var(--muted)]">
                {p.topic || "No topic set"}
              </p>
              {p.description && (
                <p className="mt-2 line-clamp-2 text-xs text-[var(--muted)]">{p.description}</p>
              )}
              <div className="mt-4 flex gap-4 text-xs">
                <Stat label="Library" value={p.library} />
                <Stat label="Reviews" value={p.curated_reviews} />
                <Stat label="Cited" value={p.cited} />
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div>
      <div className="text-sm font-semibold">{value.toLocaleString()}</div>
      <div className="text-[10px] uppercase tracking-wide text-[var(--muted)]">{label}</div>
    </div>
  );
}

function SkeletonGrid() {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {Array.from({ length: 3 }).map((_, i) => (
        <div key={i} className="card h-36 animate-pulse" />
      ))}
    </div>
  );
}
