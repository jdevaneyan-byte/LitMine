"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { createProject, deleteProject, duplicateProject, listProjects, renameProject } from "@/lib/api";
import type { ProjectSummary } from "@/lib/types";
import { Plus, ArrowRight, FolderOpen, Trash2, Pencil, Copy } from "lucide-react";

export default function HomePage() {
  const [projects, setProjects] = useState<ProjectSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [deleting, setDeleting] = useState<ProjectSummary | null>(null);
  const [renamingId, setRenamingId] = useState<number | null>(null);
  const removeProject = (id: number) =>
    setProjects((cur) => (cur ? cur.filter((p) => p.id !== id) : cur));
  const reload = () => listProjects().then(setProjects).catch((e) => setError(String(e)));

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
        <div className="flex h-14 w-full items-center gap-3 px-6 lg:px-8">
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

      <div className="w-full px-6 py-8 lg:px-8">
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
          <div className="grid auto-rows-fr grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5">
            {projects.map((p) => (
              <Link
                key={p.id}
                href={`/projects/${p.id}`}
                className="card group relative flex h-full flex-col overflow-hidden p-5 pl-6 transition duration-200 hover:-translate-y-0.5 hover:border-[var(--border-strong)] hover:shadow-md"
              >
                <span
                  className="absolute inset-y-0 left-0 w-1 opacity-70 transition group-hover:opacity-100"
                  style={{ background: typeAccent(p.literature_type) }}
                />
                <div className="absolute right-2 top-2 z-10 flex items-center rounded-lg border border-[var(--border)] bg-[var(--surface)] p-0.5 opacity-0 shadow-sm transition group-hover:opacity-100">
                  <button
                    type="button"
                    onClick={(e) => { e.preventDefault(); e.stopPropagation(); setRenamingId(p.id); }}
                    className="rounded-md p-1.5 text-[var(--muted)] transition hover:bg-[var(--surface-2)] hover:text-[var(--text)]"
                    aria-label={`Rename ${p.name}`}
                    title="Rename"
                  >
                    <Pencil size={14} />
                  </button>
                  <button
                    type="button"
                    onClick={async (e) => {
                      e.preventDefault();
                      e.stopPropagation();
                      await duplicateProject(p.id);
                      reload();
                    }}
                    className="rounded-md p-1.5 text-[var(--muted)] transition hover:bg-[var(--surface-2)] hover:text-[var(--text)]"
                    aria-label={`Duplicate ${p.name}`}
                    title="Duplicate"
                  >
                    <Copy size={14} />
                  </button>
                  <span className="mx-0.5 h-4 w-px bg-[var(--border)]" />
                  <button
                    type="button"
                    onClick={(e) => { e.preventDefault(); e.stopPropagation(); setDeleting(p); }}
                    className="rounded-md p-1.5 text-[var(--muted)] transition hover:bg-[var(--danger)]/10 hover:text-[var(--danger)]"
                    aria-label={`Delete ${p.name}`}
                    title="Delete"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
                {renamingId === p.id ? (
                  <input
                    className="input w-full text-base font-semibold"
                    defaultValue={p.name}
                    autoFocus
                    onClick={(e) => { e.preventDefault(); e.stopPropagation(); }}
                    onKeyDown={(e) => {
                      e.stopPropagation();
                      if (e.key === "Escape") setRenamingId(null);
                    }}
                    onBlur={async (e) => {
                      const name = e.target.value.trim();
                      setRenamingId(null);
                      if (name && name !== p.name) {
                        await renameProject(p.id, { name });
                        reload();
                      }
                    }}
                  />
                ) : (
                  <h2 className="line-clamp-2 pr-6 font-display text-[15px] font-semibold leading-snug">{p.name}</h2>
                )}
                <p className="mt-1.5 line-clamp-1 text-xs text-[var(--muted)]">{p.topic || "No topic set"}</p>
                {p.description && <p className="mt-2 line-clamp-2 text-xs leading-relaxed text-[var(--faint)]">{p.description}</p>}
                <div className="mt-auto flex items-end justify-between pt-5">
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
      {deleting && (
        <DeleteProjectModal
          project={deleting}
          onClose={() => setDeleting(null)}
          onDeleted={() => {
            removeProject(deleting.id);
            setDeleting(null);
          }}
        />
      )}
    </div>
  );
}

function DeleteProjectModal({
  project,
  onClose,
  onDeleted,
}: {
  project: ProjectSummary;
  onClose: () => void;
  onDeleted: () => void;
}) {
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const armed = confirm.trim().toLowerCase() === "delete";

  const run = async () => {
    if (!armed) return;
    setBusy(true);
    setErr(null);
    try {
      await deleteProject(project.id);
      onDeleted();
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
        <h2 className="font-display text-lg font-semibold text-[var(--danger)]">Delete project</h2>
        <p className="mt-2 text-sm text-[var(--text)]">
          This permanently deletes <b>{project.name}</b>, including{" "}
          <b>{project.library.toLocaleString()}</b> library papers,{" "}
          <b>{project.curated_reviews.toLocaleString()}</b> reviews, and{" "}
          <b>{project.cited.toLocaleString()}</b> cited records. This cannot be undone.
        </p>
        <label className="mt-4 block text-xs font-medium text-[var(--muted)]">
          Type <code className="font-mono text-[var(--text)]">delete</code> to confirm
        </label>
        <input
          className="input mt-1 w-full"
          value={confirm}
          autoFocus
          onChange={(e) => setConfirm(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && run()}
        />
        {err && <div className="mt-2 text-xs text-[var(--danger)]">{err}</div>}
        <div className="mt-5 flex justify-end gap-2">
          <button className="btn" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button
            className="btn"
            style={{ background: "var(--danger)", color: "white", opacity: armed && !busy ? 1 : 0.5 }}
            disabled={!armed || busy}
            onClick={run}
          >
            {busy ? "Deleting…" : "Delete this project"}
          </button>
        </div>
      </div>
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

// Subtle left-edge accent so card types are scannable without a verbose badge.
function typeAccent(literatureType: string): string {
  const t = (literatureType || "").toLowerCase();
  if (t.startsWith("review article")) return "#7c3aed"; // reviews — violet
  if (t.startsWith("research article")) return "#0d9488"; // research — teal
  return "#3b82f6"; // both — blue
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
