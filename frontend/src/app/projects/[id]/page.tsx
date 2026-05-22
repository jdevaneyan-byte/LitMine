"use client";

import { use, useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  bulkDecision,
  bulkTrash,
  exportUrl,
  getProject,
  getScreeningStats,
  listArticles,
  type ScreeningStats,
} from "@/lib/api";
import type { Article, Project } from "@/lib/types";
import NetworkMap from "@/components/NetworkMap";
import Trash from "@/components/Trash";
import SearchPanel from "@/components/SearchPanel";
import ArticleModal from "@/components/ArticleModal";
import Analysis from "@/components/Analysis";
import CommandPalette, { type Command } from "@/components/CommandPalette";
import { ShortcutsBar, HelpOverlay } from "@/components/Shortcuts";
import { Library as LibraryIcon, Search as SearchIcon, LineChart, Share2, Trash2, Command as CommandIcon, Keyboard, ArrowLeft, Menu, X } from "lucide-react";

const NAV = [
  { key: "library", label: "Library", Icon: LibraryIcon },
  { key: "search", label: "Search", Icon: SearchIcon },
  { key: "analysis", label: "Analysis", Icon: LineChart },
  { key: "network", label: "Network map", Icon: Share2 },
  { key: "trash", label: "Trash", Icon: Trash2 },
] as const;

const TAB_TITLE: Record<string, string> = {
  library: "Library",
  search: "Search & collect",
  analysis: "Analysis",
  network: "Network map",
  trash: "Trash",
};

const DECISIONS = ["all", "unscreened", "include", "maybe", "exclude"];
const PAGE = 50;

type Tab = "search" | "library" | "analysis" | "network" | "trash";

function typeFromLabel(label?: string): string {
  const l = (label || "").toLowerCase();
  if (l.startsWith("review article")) return "review";
  if (l.startsWith("research article")) return "research";
  return "both";
}

export default function ProjectPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const projectId = Number(id);

  const [project, setProject] = useState<Project | null>(null);
  const [tab, setTab] = useState<Tab>("library");
  // Jump to the Library and open a paper's modal — in edit mode or view mode
  // (e.g. command-palette paper search).
  const [focusTarget, setFocusTarget] = useState<{ id: number; edit: boolean } | null>(null);
  // Library decision filter + screening tallies live at the page level so the
  // stat cards can sit in the header (above the tab bar) and stay clickable.
  const [decision, setDecision] = useState("all");
  const [dataVersion, setDataVersion] = useState(0);
  const [stats, setStats] = useState<ScreeningStats | null>(null);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  const [navOpen, setNavOpen] = useState(false); // mobile sidebar drawer
  const go = (t: Tab) => { setTab(t); setNavOpen(false); };
  const gPrefix = useRef(0);
  const bumpData = () => setDataVersion((v) => v + 1);

  const focusInLibrary = (id: number, edit = false) => {
    setFocusTarget({ id, edit });
    setTab("library");
  };

  const searchPapers = async (q: string): Promise<Command[]> => {
    const r = await listArticles(projectId, { q, limit: 8 });
    return r.items.map((a) => ({
      id: `paper-${a.id}`,
      group: "Paper",
      label: a.title,
      hint: a.year ? String(a.year) : undefined,
      run: () => focusInLibrary(a.id, false),
    }));
  };

  useEffect(() => {
    getProject(projectId).then(setProject).catch(() => setProject(null));
  }, [projectId]);

  useEffect(() => {
    if (tab !== "library") return;
    getScreeningStats(projectId).then(setStats).catch(() => setStats(null));
  }, [projectId, tab, dataVersion]);

  // Global keys: Cmd/Ctrl+K palette, ? help, and "g then s/l/n/d/t" tab nav.
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOpen((o) => !o);
        return;
      }
      const el = document.activeElement as HTMLElement | null;
      const typing = el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.isContentEditable);
      if (typing || e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.key === "?") {
        e.preventDefault();
        setHelpOpen((o) => !o);
        return;
      }
      const k = e.key.toLowerCase();
      const now = Date.now();
      if (k === "g") {
        gPrefix.current = now;
        return;
      }
      if (now - gPrefix.current < 900) {
        const map: Record<string, Tab> = { s: "search", l: "library", a: "analysis", n: "network", t: "trash" };
        if (map[k]) {
          e.preventDefault();
          setTab(map[k]);
          gPrefix.current = 0;
        }
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  const commands: Command[] = [
    { id: "go-search", group: "Go to", label: "Search", hint: "g s", run: () => setTab("search") },
    { id: "go-library", group: "Go to", label: "Library", hint: "g l", run: () => setTab("library") },
    { id: "go-network", group: "Go to", label: "Network map", hint: "g n", run: () => setTab("network") },
    { id: "go-analysis", group: "Go to", label: "Analysis", hint: "g a", run: () => setTab("analysis") },
    { id: "go-trash", group: "Go to", label: "Trash", hint: "g t", run: () => setTab("trash") },
    { id: "exp-csv", group: "Export", label: "Download CSV", run: () => window.open(exportUrl(projectId, "csv")) },
    { id: "exp-json", group: "Export", label: "Download JSON", run: () => window.open(exportUrl(projectId, "json")) },
    { id: "exp-xlsx", group: "Export", label: "Download Excel", run: () => window.open(exportUrl(projectId, "xlsx")) },
    { id: "help", group: "Help", label: "Keyboard shortcuts", hint: "?", run: () => setHelpOpen(true) },
  ];

  // A freshly-created project lands here with ?tab=search so collection starts immediately.
  useEffect(() => {
    const t = new URLSearchParams(window.location.search).get("tab");
    if (t && ["search", "library", "analysis", "network", "trash"].includes(t)) {
      setTab(t as Tab);
    }
  }, []);

  return (
    <div className="flex min-h-screen">
      {/* Mobile scrim */}
      {navOpen && <div className="fixed inset-0 z-30 bg-black/50 backdrop-blur-sm md:hidden" onClick={() => setNavOpen(false)} />}

      {/* ── Dark navigation rail (drawer on mobile, fixed on desktop) ── */}
      <aside
        className={`fixed inset-y-0 left-0 z-40 flex h-screen w-[244px] shrink-0 flex-col gap-4 overflow-y-auto bg-[var(--rail)] px-3 py-4 text-[var(--rail-text)] shadow-2xl transition-transform duration-200 md:sticky md:top-0 md:translate-x-0 md:shadow-none ${
          navOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <button className="absolute right-3 top-3 rounded-md p-1 text-[var(--rail-muted)] hover:bg-[var(--rail-2)] hover:text-white md:hidden" onClick={() => setNavOpen(false)} aria-label="Close menu">
          <X size={18} />
        </button>
        {/* Brand */}
        <Link href="/" className="flex items-center gap-2.5 px-2 py-1">
          <span className="grid h-8 w-8 place-items-center rounded-lg bg-gradient-to-br from-[#3b82f6] to-[#1e40af] text-xs font-bold text-white shadow-[0_2px_8px_-2px_rgba(59,130,246,0.6)]">
            LM
          </span>
          <span className="font-display text-[15px] font-bold tracking-tight text-white">LitMine</span>
        </Link>

        {/* Project context */}
        <div className="rounded-xl bg-[var(--rail-2)] px-3 py-2.5">
          <Link href="/" className="mb-1.5 flex items-center gap-1 text-[11px] font-medium text-[var(--rail-muted)] hover:text-white">
            <ArrowLeft size={12} /> All projects
          </Link>
          <div className="line-clamp-2 font-display text-sm font-semibold text-white">{project?.name ?? "Loading…"}</div>
          {project?.topic && <div className="mt-0.5 line-clamp-1 text-[11px] text-[var(--rail-muted)]">{project.literature_type}</div>}
        </div>

        {/* Primary nav */}
        <nav className="flex flex-col gap-0.5">
          {NAV.map(({ key, label, Icon }) => (
            <button key={key} className="rail-item" data-active={tab === key} onClick={() => go(key as Tab)}>
              <Icon size={16} strokeWidth={2} />
              {label}
            </button>
          ))}
        </nav>

        {/* Screening stats */}
        {stats && (
          <div className="mt-1">
            <div className="px-2 pb-1.5 text-[10px] font-semibold uppercase tracking-wider text-[var(--rail-muted)]">Screening</div>
            <div className="flex flex-col gap-0.5">
              <RailStat label="Total" value={stats.total} dot="#3b82f6" active={tab === "library" && decision === "all"} onClick={() => { go("library"); setDecision("all"); }} />
              <RailStat label="Unscreened" value={stats.unscreened} dot="#64748b" active={tab === "library" && decision === "unscreened"} onClick={() => { go("library"); setDecision("unscreened"); }} />
              <RailStat label="Include" value={stats.include} dot="#22c55e" active={tab === "library" && decision === "include"} onClick={() => { go("library"); setDecision("include"); }} />
              <RailStat label="Maybe" value={stats.maybe} dot="#f59e0b" active={tab === "library" && decision === "maybe"} onClick={() => { go("library"); setDecision("maybe"); }} />
              <RailStat label="Exclude" value={stats.exclude} dot="#ef4444" active={tab === "library" && decision === "exclude"} onClick={() => { go("library"); setDecision("exclude"); }} />
            </div>
          </div>
        )}

        <div className="mt-auto flex items-center gap-1 px-2 pt-2 text-[10px] text-[var(--rail-muted)]">
          <span className="h-1.5 w-1.5 rounded-full bg-[#22c55e]" /> Local-first · synced
        </div>
      </aside>

      {/* ── Light data canvas ────────────────────────────────────────── */}
      <div className="flex min-h-screen min-w-0 flex-1 flex-col">
        {/* Top bar */}
        <header className="sticky top-0 z-20 flex h-14 shrink-0 items-center gap-3 border-b border-[var(--border)] bg-[var(--surface)]/85 px-5 backdrop-blur">
          <button className="btn btn-ghost px-2 md:hidden" onClick={() => setNavOpen(true)} aria-label="Open menu">
            <Menu size={18} />
          </button>
          <h1 className="font-display text-base font-semibold tracking-tight">{TAB_TITLE[tab]}</h1>
          {project?.topic && tab === "library" && (
            <span className="hidden truncate text-xs text-[var(--muted)] lg:inline">· {project.topic}</span>
          )}
          <div className="ml-auto flex items-center gap-1.5">
            <button onClick={() => setPaletteOpen(true)} className="btn btn-ghost gap-1.5 text-xs" title="Command palette (⌘K)">
              <CommandIcon size={14} /> <span className="hidden sm:inline">Commands</span>
              <kbd className="ml-1 hidden rounded border border-[var(--border)] bg-[var(--surface-2)] px-1 py-0.5 text-[10px] font-medium sm:inline">⌘K</kbd>
            </button>
            <button onClick={() => setHelpOpen(true)} className="btn btn-ghost px-2 text-xs" title="Keyboard shortcuts (?)">
              <Keyboard size={14} />
            </button>
            <div className="mx-1 h-5 w-px bg-[var(--border)]" />
            <div className="flex overflow-hidden rounded-[var(--radius-sm)] border border-[var(--border-strong)]">
              {(["csv", "json", "xlsx"] as const).map((f) => (
                <button
                  key={f}
                  onClick={() => window.open(exportUrl(projectId, f))}
                  className="border-r border-[var(--border)] bg-[var(--surface)] px-2.5 py-1.5 text-[11px] font-medium uppercase text-[var(--muted)] transition last:border-r-0 hover:bg-[var(--surface-2)] hover:text-[var(--text)]"
                  title={`Export ${f.toUpperCase()}`}
                >
                  {f}
                </button>
              ))}
            </div>
          </div>
        </header>

        {/* Content */}
        <main className="min-w-0 flex-1 p-5">
          <ShortcutsBar context={tab} onHelp={() => setHelpOpen(true)} />

          {tab === "search" && (
            <SearchPanel projectId={projectId} defaultType={typeFromLabel(project?.literature_type)} topic={project?.topic ?? ""} onViewLibrary={() => setTab("library")} />
          )}
          {tab === "library" && (
            <LibraryTab
              projectId={projectId}
              decision={decision}
              setDecision={setDecision}
              dataVersion={dataVersion}
              onChanged={bumpData}
              stats={stats}
              focusId={focusTarget?.id ?? null}
              focusEdit={focusTarget?.edit ?? false}
              onFocusConsumed={() => setFocusTarget(null)}
            />
          )}
          {tab === "analysis" && (
            <Analysis projectId={projectId} onChanged={bumpData} onOpenPaper={(id) => { setTab("library"); focusInLibrary(id, false); }} />
          )}
          {tab === "network" && (
            <NetworkMap projectId={projectId} onOpenPaper={(id) => { setTab("library"); focusInLibrary(id, false); }} />
          )}
          {tab === "trash" && <Trash projectId={projectId} />}
        </main>
      </div>

      <CommandPalette open={paletteOpen} commands={commands} onSearch={searchPapers} onClose={() => setPaletteOpen(false)} />
      <HelpOverlay open={helpOpen} onClose={() => setHelpOpen(false)} />
    </div>
  );
}

function RailStat({ label, value, dot, active, onClick }: { label: string; value: number; dot: string; active?: boolean; onClick?: () => void }) {
  return (
    <button
      onClick={onClick}
      data-active={active}
      className="group flex items-center gap-2.5 rounded-[var(--radius-sm)] px-3 py-1.5 text-[13px] transition hover:bg-[var(--rail-2)] data-[active=true]:bg-[var(--rail-active-bg)]"
    >
      <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: dot }} />
      <span className="text-[var(--rail-text)] group-hover:text-white group-data-[active=true]:font-semibold group-data-[active=true]:text-white">{label}</span>
      <span className="tnum ml-auto font-mono text-[12px] text-[var(--rail-muted)] group-data-[active=true]:text-white">{value.toLocaleString()}</span>
    </button>
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

function LibraryTab({
  projectId,
  decision,
  setDecision,
  dataVersion = 0,
  onChanged,
  stats,
  focusId = null,
  focusEdit = false,
  onFocusConsumed,
}: {
  projectId: number;
  decision: string;
  setDecision: (d: string) => void;
  dataVersion?: number;
  onChanged?: () => void;
  stats?: ScreeningStats | null;
  focusId?: number | null;
  focusEdit?: boolean;
  onFocusConsumed?: () => void;
}) {
  const [items, setItems] = useState<Article[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState("");
  const [category, setCategory] = useState("all");
  const [yearMin, setYearMin] = useState("");
  const [yearMax, setYearMax] = useState("");
  const [sort, setSort] = useState<"year" | "citations">("year");
  const [page, setPage] = useState(0);
  // Origin toggles: show keyword-collected and/or reference-harvested papers.
  const [showSearch, setShowSearch] = useState(true);
  const [showReference, setShowReference] = useState(true);
  const originParam = showSearch && showReference ? "all" : showSearch ? "search" : showReference ? "reference" : "none";
  // Modal: which article to show, an optional preloaded row, and edit mode.
  const [modalId, setModalId] = useState<number | null>(null);
  const [modalInitial, setModalInitial] = useState<Article | null>(null);
  const [modalEdit, setModalEdit] = useState(false);

  // Reset to the first page whenever the decision filter (driven from the
  // header stat cards) changes.
  useEffect(() => {
    setPage(0);
  }, [decision]);

  // Open a paper's modal when asked (edit mode, or view from the palette).
  useEffect(() => {
    if (focusId == null) return;
    const i = items.findIndex((x) => x.id === focusId);
    if (i >= 0) setFocused(i);
    setModalInitial(i >= 0 ? items[i] : null);
    setModalEdit(focusEdit);
    setModalId(focusId);
    onFocusConsumed?.();
  }, [focusId, focusEdit, onFocusConsumed]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (originParam === "none") {
      setItems([]);
      setTotal(0);
      setLoading(false);
      return;
    }
    setLoading(true);
    const handle = setTimeout(() => {
      listArticles(projectId, {
        q,
        decision,
        category,
        origin: originParam as "all" | "search" | "reference",
        year_min: yearMin ? Number(yearMin) : undefined,
        year_max: yearMax ? Number(yearMax) : undefined,
        sort,
        limit: PAGE,
        offset: page * PAGE,
      })
        .then((r) => {
          setItems(r.items);
          setTotal(r.total);
        })
        .finally(() => setLoading(false));
    }, 250); // debounce the keyword box
    return () => clearTimeout(handle);
  }, [projectId, q, decision, category, originParam, yearMin, yearMax, sort, page, dataVersion]);

  const [focused, setFocused] = useState(0);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const searchRef = useRef<HTMLInputElement>(null);
  const rowsRef = useRef<HTMLTableSectionElement>(null);
  const pendingOpen = useRef<null | "first" | "last" | "same">(null);

  // When the result set changes, clear selection and reset the cursor — but
  // NOT while a modal is open (deciding/editing reloads the list in the
  // background, and we must keep your place on the open paper).
  useEffect(() => {
    setSelected(new Set());
    if (modalId == null) setFocused(0);
  }, [items]); // eslint-disable-line react-hooks/exhaustive-deps

  const openRow = (a: Article) => {
    const i = items.findIndex((x) => x.id === a.id);
    if (i >= 0) setFocused(i);
    setModalInitial(a);
    setModalEdit(false);
    setModalId(a.id);
  };

  // Move the open modal to the previous/next paper — crossing page boundaries
  // by loading the adjacent page and opening its first/last paper.
  const gotoRel = (delta: number) => {
    const ni = focused + delta;
    if (ni < 0) {
      if (page > 0) {
        pendingOpen.current = "last";
        setPage((p) => p - 1);
      }
      return;
    }
    if (ni >= items.length) {
      if (page < pages - 1) {
        pendingOpen.current = "first";
        setPage((p) => p + 1);
      }
      return;
    }
    setFocused(ni);
    setModalInitial(items[ni]);
    setModalEdit(false);
    setModalId(items[ni].id);
  };

  // After the list reloads from a page-flip (gotoRel) or a delete, re-open the
  // right paper: first/last of the new page, or — after a delete — whatever
  // shifted into the same slot (the "next" paper). Close if nothing's left.
  useEffect(() => {
    const mode = pendingOpen.current;
    if (mode == null) return;
    pendingOpen.current = null;
    if (items.length === 0) {
      setModalId(null);
      return;
    }
    const idx = mode === "first" ? 0 : mode === "last" ? items.length - 1 : Math.min(focused, items.length - 1);
    setFocused(idx);
    setModalInitial(items[idx]);
    setModalEdit(false);
    setModalId(items[idx].id);
  }, [items]); // eslint-disable-line react-hooks/exhaustive-deps

  const pages = Math.max(1, Math.ceil(total / PAGE));

  // Apply a decision to the current selection (if any) or the focused row,
  // then advance. Used by both buttons and keyboard.
  const applyDecision = async (status: string) => {
    const ids = selected.size > 0 ? [...selected] : items[focused] ? [items[focused].id] : [];
    if (ids.length === 0) return;
    await bulkDecision(projectId, ids, status);
    if (selected.size > 0) setSelected(new Set());
    else setFocused((f) => Math.min(f + 1, items.length - 1));
    onChanged?.();
  };

  const trashSelectionOrFocused = async () => {
    const ids = selected.size > 0 ? [...selected] : items[focused] ? [items[focused].id] : [];
    if (ids.length === 0) return;
    await bulkTrash(projectId, ids);
    setSelected(new Set());
    onChanged?.();
  };

  const toggleSelect = (id: number) =>
    setSelected((s) => {
      const next = new Set(s);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  // Delete the open paper, then advance to the paper that takes its slot
  // (the "next" one) instead of closing the modal.
  const deleteCurrent = async () => {
    if (modalId == null) return;
    await bulkTrash(projectId, [modalId]);
    pendingOpen.current = "same";
    onChanged?.();
  };

  // "Viewed" markers — which papers you've opened — persisted per project in
  // localStorage so the list shows what you've already looked at.
  const [viewed, setViewed] = useState<Set<number>>(new Set());
  useEffect(() => {
    try {
      setViewed(new Set(JSON.parse(localStorage.getItem(`litmine-viewed-${projectId}`) || "[]")));
    } catch {
      setViewed(new Set());
    }
  }, [projectId]);
  useEffect(() => {
    if (modalId == null) return;
    setViewed((s) => {
      if (s.has(modalId)) return s;
      const n = new Set(s).add(modalId);
      try {
        localStorage.setItem(`litmine-viewed-${projectId}`, JSON.stringify([...n]));
      } catch {}
      return n;
    });
  }, [modalId, projectId]);

  // Keyboard control for the library (disabled while a modal is open).
  useEffect(() => {
    if (modalId != null) return;
    const handler = (e: KeyboardEvent) => {
      const el = document.activeElement as HTMLElement | null;
      const typing = el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.isContentEditable);
      if (typing) {
        if (e.key === "Escape") (el as HTMLElement).blur();
        return;
      }
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const k = e.key.toLowerCase();
      const max = items.length - 1;
      const nav = (n: number) => {
        e.preventDefault();
        setFocused((f) => Math.max(0, Math.min(f + n, max)));
      };
      if (k === "j" || e.key === "ArrowDown") return nav(1);
      if (k === "k" || e.key === "ArrowUp") return nav(-1);
      if (k === "o" || e.key === "Enter") {
        if (items[focused]) { e.preventDefault(); openRow(items[focused]); }
        return;
      }
      if (k === "i") { e.preventDefault(); applyDecision("include"); return; }
      if (k === "m") { e.preventDefault(); applyDecision("maybe"); return; }
      if (k === "e") { e.preventDefault(); applyDecision("exclude"); return; }
      if (k === "u") { e.preventDefault(); applyDecision("unscreened"); return; }
      if (k === "x" || e.key === " ") {
        if (items[focused]) { e.preventDefault(); toggleSelect(items[focused].id); }
        return;
      }
      if (k === "a") { e.preventDefault(); setSelected(new Set(items.map((a) => a.id))); return; }
      if (e.key === "Delete" || e.key === "Backspace") { e.preventDefault(); trashSelectionOrFocused(); return; }
      if (k === "[") { e.preventDefault(); setPage((p) => Math.max(0, p - 1)); return; }
      if (k === "]") { e.preventDefault(); setPage((p) => Math.min(pages - 1, p + 1)); return; }
      if (k === "/") { e.preventDefault(); searchRef.current?.focus(); return; }
      if (["1", "2", "3", "4", "5"].includes(k)) {
        e.preventDefault();
        setDecision(["all", "unscreened", "include", "maybe", "exclude"][Number(k) - 1]);
        return;
      }
      if (e.key === "Escape" && selected.size) { setSelected(new Set()); return; }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [modalId, items, focused, selected, pages]); // eslint-disable-line react-hooks/exhaustive-deps

  // Keep the focused row scrolled into view.
  useEffect(() => {
    const row = rowsRef.current?.querySelectorAll("tr")[focused] as HTMLElement | undefined;
    row?.scrollIntoView({ block: "nearest" });
  }, [focused]);

  return (
    <div className="flex h-[calc(100vh-12rem)] min-h-[30rem] flex-col">
      <div className="mb-3 flex shrink-0 flex-wrap items-center gap-2">
        <input
          ref={searchRef}
          className="input max-w-xs"
          placeholder="Filter by title…  ( / )"
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
        <div className="flex items-center gap-1" title="Year range">
          <input
            className="input w-20"
            placeholder="from"
            value={yearMin}
            inputMode="numeric"
            onChange={(e) => {
              setPage(0);
              setYearMin(e.target.value.replace(/\D/g, ""));
            }}
          />
          <span className="text-xs text-[var(--muted)]">–</span>
          <input
            className="input w-20"
            placeholder="to"
            value={yearMax}
            inputMode="numeric"
            onChange={(e) => {
              setPage(0);
              setYearMax(e.target.value.replace(/\D/g, ""));
            }}
          />
        </div>
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
        <OriginChip
          label="Keyword"
          count={stats?.from_search}
          active={showSearch}
          onClick={() => { setPage(0); setShowSearch((v) => !v); }}
        />
        <OriginChip
          label="References"
          count={stats?.from_reference}
          active={showReference}
          tone="#0ea5e9"
          onClick={() => { setPage(0); setShowReference((v) => !v); }}
        />
        <div className="ml-auto flex items-center gap-1.5 rounded-full bg-[var(--surface-2)] px-3 py-1 text-xs">
          <span className="tnum font-mono font-semibold text-[var(--text)]">{total.toLocaleString()}</span>
          <span className="text-[var(--muted)]">papers</span>
        </div>
      </div>

      {selected.size > 0 && (
        <div className="mb-2 flex shrink-0 flex-wrap items-center gap-2 rounded-md border border-[var(--primary)] bg-[var(--primary-weak)] px-3 py-2 text-sm">
          <span className="font-medium text-[var(--primary)]">{selected.size} selected</span>
          <button className="btn px-2 py-1 text-xs" onClick={() => applyDecision("include")}>Include</button>
          <button className="btn px-2 py-1 text-xs" onClick={() => applyDecision("maybe")}>Maybe</button>
          <button className="btn px-2 py-1 text-xs" onClick={() => applyDecision("exclude")}>Exclude</button>
          <button className="btn px-2 py-1 text-xs" onClick={() => applyDecision("unscreened")}>Unscreen</button>
          <button className="btn px-2 py-1 text-xs text-[#b91c1c]" onClick={trashSelectionOrFocused}>Delete</button>
          <button className="btn ml-auto px-2 py-1 text-xs" onClick={() => setSelected(new Set())}>Clear</button>
        </div>
      )}

      <div className="card flex min-h-0 flex-1 flex-col overflow-hidden">
        <div className="min-h-0 flex-1 overflow-y-auto">
        <table className="w-full text-sm">
          <thead className="sticky top-0 z-10">
            <tr className="border-b border-[var(--border-strong)] bg-[var(--surface-2)] text-left text-[11px] font-semibold uppercase tracking-wider text-[var(--muted)] shadow-[0_1px_0_rgba(15,23,42,0.04)]">
              <th className="w-8 px-2 py-2.5"></th>
              <th className="px-3 py-2.5">#</th>
              <th className="px-3 py-2.5">Title</th>
              <th className="px-3 py-2.5">Year</th>
              <th className="px-3 py-2.5 text-right">Citations</th>
              <th className="px-3 py-2.5 text-right" title="References fetched for this paper; green = all collectable ones are in your library">
                Refs
              </th>
              <th className="px-3 py-2.5">Type</th>
              <th className="px-3 py-2.5">Source</th>
              <th className="px-3 py-2.5">Decision</th>
            </tr>
          </thead>
          <tbody ref={rowsRef}>
            {loading &&
              Array.from({ length: 8 }).map((_, i) => (
                <tr key={i} className="border-b">
                  <td colSpan={9} className="px-3 py-3">
                    <div className="h-4 animate-pulse rounded bg-[var(--bg)]" />
                  </td>
                </tr>
              ))}
            {!loading &&
              items.map((a, i) => {
                const isFocused = i === focused;
                const isSel = selected.has(a.id);
                return (
                  <tr
                    key={a.id}
                    onClick={() => openRow(a)}
                    onMouseEnter={() => setFocused(i)}
                    className={`cursor-pointer border-b last:border-0 ${
                      isSel ? "bg-[var(--primary-weak)]" : isFocused ? "bg-[var(--surface-2)]" : "hover:bg-[var(--surface-2)]"
                    } ${isFocused ? "ring-1 ring-inset ring-[var(--primary)]" : ""}`}
                  >
                    <td className="w-8 px-2 py-2" onClick={(e) => e.stopPropagation()}>
                      <input
                        type="checkbox"
                        checked={isSel}
                        onChange={() => toggleSelect(a.id)}
                        aria-label="Select row"
                      />
                    </td>
                    <td className="px-3 py-2 text-[var(--muted)]">
                      <span className="inline-flex items-center gap-1.5">
                        <span
                          className="h-1.5 w-1.5 rounded-full"
                          style={{ background: viewed.has(a.id) ? "var(--primary)" : "transparent" }}
                          title={viewed.has(a.id) ? "Viewed" : undefined}
                        />
                        {page * PAGE + i + 1}
                      </span>
                    </td>
                    <td className="px-3 py-2">
                      <span className={`line-clamp-2 ${viewed.has(a.id) ? "text-[var(--muted)]" : ""}`}>
                        {a.origin === "reference" && (
                          <span
                            className="mr-1.5 rounded px-1 py-0.5 align-middle text-[9px] font-semibold uppercase"
                            style={{ background: "#0ea5e933", color: "#0369a1" }}
                            title="Harvested from a reference list"
                          >
                            ref
                          </span>
                        )}
                        {a.title}
                      </span>
                      <span className="text-xs text-[var(--muted)]">{a.authors}</span>
                    </td>
                    <td className="tnum px-3 py-2 font-mono text-[12px] text-[var(--text-2)]">{a.year ?? ""}</td>
                    <td className="tnum px-3 py-2 text-right font-mono text-[12px] text-[var(--text-2)]">
                      {a.citation_count != null ? a.citation_count.toLocaleString() : <span className="text-[var(--faint)]">—</span>}
                    </td>
                    <td className="tnum px-3 py-2 text-right font-mono text-[12px]">
                      {(a.references_count ?? 0) === 0 ? (
                        <span className="text-[var(--muted)]">—</span>
                      ) : (
                        <span
                          className="font-medium"
                          style={{
                            color:
                              (a.references_with_doi ?? 0) > 0 && (a.references_in_library ?? 0) >= (a.references_with_doi ?? 0)
                                ? "var(--success)"
                                : "var(--text)",
                          }}
                          title={`${a.references_count} references · ${a.references_in_library ?? 0}/${a.references_with_doi ?? 0} with a DOI already in your library — click to view`}
                        >
                          {a.references_count}
                        </span>
                      )}
                    </td>
                    <td className="px-3 py-2 text-xs text-[var(--muted)]">{a.category || "Unclassified"}</td>
                    <td className="px-3 py-2 text-xs text-[var(--muted)]">{a.source}</td>
                    <td className="px-3 py-2">
                      <DecisionBadge value={a.screening_status} />
                    </td>
                  </tr>
                );
              })}
            {!loading && items.length === 0 && (
              <tr>
                <td colSpan={9} className="px-3 py-8 text-center text-sm text-[var(--muted)]">
                  No matching papers.
                </td>
              </tr>
            )}
          </tbody>
        </table>
        </div>
      </div>

      <div className="mt-3 flex shrink-0 items-center justify-between text-sm">
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

      {modalId != null && (
        <ArticleModal
          articleId={modalId}
          initial={modalInitial}
          startInEdit={modalEdit}
          stats={stats}
          position={{ index: page * PAGE + focused, total }}
          onPrev={() => gotoRel(-1)}
          onNext={() => gotoRel(1)}
          hasPrev={focused > 0 || page > 0}
          hasNext={focused < items.length - 1 || page < pages - 1}
          onDelete={deleteCurrent}
          onClose={() => setModalId(null)}
          onChanged={onChanged}
          onOpenArticle={(id) => {
            setModalInitial(null);
            setModalEdit(false);
            setModalId(id);
          }}
        />
      )}
    </div>
  );
}

function OriginChip({
  label,
  count,
  active,
  tone = "var(--primary)",
  onClick,
}: {
  label: string;
  count?: number;
  active: boolean;
  tone?: string;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      title={active ? `Hide ${label}` : `Show ${label}`}
      className={`flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs transition ${
        active ? "border-[var(--border)] text-[var(--text)]" : "border-transparent text-[var(--muted)] opacity-60"
      }`}
    >
      <span className="h-2 w-2 rounded-full" style={{ background: active ? tone : "var(--muted)" }} />
      {label}
      {count != null && <span className="tabular-nums text-[var(--muted)]">{count.toLocaleString()}</span>}
    </button>
  );
}

function DecisionBadge({ value }: { value: string }) {
  const v = value || "unscreened";
  const cls =
    v === "include" ? "badge-include" : v === "maybe" ? "badge-maybe" : v === "exclude" ? "badge-exclude" : "";
  return <span className={`badge ${cls}`}>{v}</span>;
}
