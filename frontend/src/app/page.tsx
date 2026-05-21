"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { createProject, listProjects } from "@/lib/api";
import type { ProjectSummary } from "@/lib/types";
import { Plus, ArrowRight, FolderOpen } from "lucide-react";

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
    <div className="relative min-h-screen">
      {/* Subtle ambient backdrop so the page reads as a designed surface, not a blank sheet */}
      <div
        className="pointer-events-none fixed inset-0 -z-10"
        style={{
          background:
            "radial-gradient(1200px 500px at 15% -10%, rgba(59,130,246,0.07), transparent 60%), radial-gradient(900px 500px at 100% 0%, rgba(217,119,6,0.05), transparent 55%)",
        }}
      />
      {/* Top bar */}
      <header className="sticky top-0 z-20 border-b border-[var(--border)] bg-[var(--surface)]/85 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-7xl items-center gap-3 px-8">
          <span className="grid h-8 w-8 place-items-center rounded-lg bg-gradient-to-br from-[#3b82f6] to-[#1e40af] text-xs font-bold text-white shadow-[0_2px_8px_-2px_rgba(59,130,246,0.5)]">
            LM
          </span>
          <span className="font-display text-[15px] font-bold tracking-tight">LitMine</span>
          <span className="hidden text-xs text-[var(--muted)] sm:inline">· local-first literature workspace</span>
          <button className="btn btn-primary ml-auto" onClick={() => setCreating(true)}>
            <Plus size={15} /> New project
          </button>
        </div>
      </header>

      <div className="mx-auto max-w-7xl px-8 py-10">
        <div className="mb-7">
          <h1 className="font-display text-[28px] font-bold leading-tight tracking-tight">Projects</h1>
          <p className="mt-1.5 text-sm text-[var(--muted)]">
            Create a project, collect literature, then screen, analyze, and explore its citation network.
          </p>
        </div>

        {error && (
          <div className="card border-[var(--danger)]/30 p-4 text-sm text-[var(--danger)]">
            Could not reach the API at <code className="font-mono">{process.env.NEXT_PUBLIC_API_BASE}</code>. Is the backend running?
            <br />
            <span className="text-[var(--muted)]">{error}</span>
          </div>
        )}

        {!projects && !error && <SkeletonGrid />}

        {projects && projects.length === 0 && (
          <div className="card flex flex-col items-center gap-3 p-12 text-center">
            <span className="grid h-12 w-12 place-items-center rounded-2xl bg-[var(--primary-weak)] text-[var(--primary)]">
              <FolderOpen size={22} />
            </span>
            <div className="text-sm text-[var(--muted)]">No projects yet — create your first to start collecting.</div>
            <button className="btn btn-primary" onClick={() => setCreating(true)}>
              <Plus size={15} /> New project
            </button>
          </div>
        )}

        {projects && projects.length > 0 && (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4">
            {projects.map((p) => (
              <Link
                key={p.id}
                href={`/projects/${p.id}`}
                className="card group relative block overflow-hidden p-5 transition duration-200 hover:-translate-y-0.5 hover:shadow-md"
              >
                <span className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-[#3b82f6] to-[#1e40af] opacity-0 transition group-hover:opacity-100" />
                <div className="flex items-start justify-between gap-2">
                  <h2 className="font-display text-base font-semibold leading-snug">{p.name}</h2>
                  <span className="badge shrink-0">{p.literature_type}</span>
                </div>
                <p className="mt-1 line-clamp-1 text-xs text-[var(--muted)]">{p.topic || "No topic set"}</p>
                {p.description && <p className="mt-2 line-clamp-2 text-xs text-[var(--muted)]">{p.description}</p>}
                <div className="mt-4 flex items-end justify-between">
                  <div className="flex gap-5 text-xs">
                    <Stat label="Library" value={p.library} />
                    <Stat label="Reviews" value={p.curated_reviews} />
                    <Stat label="Cited" value={p.cited} />
                  </div>
                  <ArrowRight size={16} className="text-[var(--faint)] transition group-hover:translate-x-0.5 group-hover:text-[var(--primary)]" />
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>

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
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm"
      onClick={onClose}
    >
      <div className="card card-elevated w-full max-w-md p-5" onClick={(e) => e.stopPropagation()}>
        <h2 className="font-display text-lg font-semibold">New project</h2>
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
      <div className="tnum font-mono text-sm font-semibold text-[var(--text)]">{value.toLocaleString()}</div>
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
