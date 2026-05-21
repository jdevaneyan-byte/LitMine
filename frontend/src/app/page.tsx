"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { createProject, listProjects } from "@/lib/api";
import type { ProjectSummary } from "@/lib/types";

export default function HomePage() {
  const [projects, setProjects] = useState<ProjectSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    listProjects()
      .then(setProjects)
      .catch((e) => setError(String(e)));
  }, []);

  return (
    <div>
      <div className="mb-6 flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Projects</h1>
          <p className="mt-1 text-sm text-[var(--muted)]">
            Create a project, collect literature, then read, review, and explore its network.
          </p>
        </div>
        <button className="btn btn-primary shrink-0" onClick={() => setCreating(true)}>
          + New project
        </button>
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
          No projects yet.{" "}
          <button className="text-[var(--primary)] underline" onClick={() => setCreating(true)}>
            Create your first project
          </button>{" "}
          to start collecting.
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

      {creating && <NewProjectModal onClose={() => setCreating(false)} />}
    </div>
  );
}

const TYPES = [
  ["both", "Review + research"],
  ["review", "Reviews only"],
  ["research", "Research only"],
] as const;

function NewProjectModal({ onClose }: { onClose: () => void }) {
  const router = useRouter();
  const [name, setName] = useState("");
  const [topic, setTopic] = useState("");
  const [type, setType] = useState("both");
  const [description, setDescription] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const submit = async () => {
    if (!name.trim() || !topic.trim()) {
      setErr("Name and topic are required.");
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      const p = await createProject({ name: name.trim(), topic: topic.trim(), type, description });
      router.push(`/projects/${p.id}?tab=search`);
    } catch (e) {
      setErr(String(e));
      setBusy(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={onClose}
    >
      <div className="card w-full max-w-md p-5" onClick={(e) => e.stopPropagation()}>
        <h2 className="text-lg font-semibold">New project</h2>
        <p className="mt-1 text-xs text-[var(--muted)]">
          Give it a name and topic. You&apos;ll collect literature on the next screen.
        </p>

        <div className="mt-4 space-y-3">
          <div>
            <label className="mb-1 block text-xs font-medium text-[var(--muted)]">Name</label>
            <input
              className="input w-full"
              placeholder="e.g. Nanoparticle drug delivery"
              value={name}
              autoFocus
              onChange={(e) => setName(e.target.value)}
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-[var(--muted)]">Topic</label>
            <input
              className="input w-full"
              placeholder="Short description of the research area"
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-[var(--muted)]">
              Literature type
            </label>
            <div className="flex gap-2">
              {TYPES.map(([val, label]) => (
                <button
                  key={val}
                  type="button"
                  onClick={() => setType(val)}
                  className={`flex-1 rounded-md border px-3 py-1.5 text-xs font-medium transition ${
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
        </div>

        {err && <div className="mt-3 text-xs text-[#b91c1c]">{err}</div>}

        <div className="mt-5 flex justify-end gap-2">
          <button className="btn" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button className="btn btn-primary" onClick={submit} disabled={busy}>
            {busy ? "Creating…" : "Create & collect →"}
          </button>
        </div>
      </div>
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
