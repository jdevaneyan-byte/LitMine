"use client";

import { useEffect } from "react";

export function Kbd({ children }: { children: React.ReactNode }) {
  return (
    <kbd className="rounded border border-[var(--border)] bg-[var(--surface-2)] px-1.5 py-0.5 font-mono text-[10px] font-semibold leading-none text-[var(--text)] shadow-sm">
      {children}
    </kbd>
  );
}

// Thin always-visible hint strip under the tabs. Context-aware.
export function ShortcutsBar({ context, onHelp }: { context: string; onHelp: () => void }) {
  const hints =
    context === "library"
      ? [
          ["j / k", "move"],
          ["o", "open"],
          ["i / m / e", "include / maybe / exclude"],
          ["u", "unscreen"],
          ["x", "select"],
          ["[ ]", "page"],
          ["/", "search"],
        ]
      : [
          ["g then s l a n t", "switch tabs"],
        ];
  return (
    <div className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-1 rounded-md border border-[var(--border)] bg-[var(--surface-2)]/50 px-3 py-1.5 text-[11px] text-[var(--muted)]">
      {hints.map(([k, label]) => (
        <span key={k} className="flex items-center gap-1.5">
          <Kbd>{k}</Kbd>
          <span>{label}</span>
        </span>
      ))}
      <span className="ml-auto flex items-center gap-3">
        <span className="flex items-center gap-1.5">
          <Kbd>⌘K</Kbd>
          <span>commands</span>
        </span>
        <button onClick={onHelp} className="flex items-center gap-1.5 hover:text-[var(--text)]">
          <Kbd>?</Kbd>
          <span>shortcuts</span>
        </button>
      </span>
    </div>
  );
}

const GROUPS: { title: string; items: [string, string][] }[] = [
  {
    title: "Navigation",
    items: [
      ["g s", "Go to Search"],
      ["g l", "Go to Library"],
      ["g n", "Go to Network map"],
      ["g a", "Go to Analysis"],
      ["g t", "Go to Trash"],
      ["⌘K / Ctrl+K", "Command palette"],
      ["?", "This help"],
      ["Esc", "Close dialog / clear"],
    ],
  },
  {
    title: "Library — navigate",
    items: [
      ["j / ↓", "Next paper"],
      ["k / ↑", "Previous paper"],
      ["o / Enter", "Open paper"],
      ["[ / ]", "Previous / next page"],
      ["/", "Focus search box"],
      ["1–5", "Filter: all / unscreened / include / maybe / exclude"],
    ],
  },
  {
    title: "Library — screen (focused or selected)",
    items: [
      ["i", "Include"],
      ["m", "Maybe"],
      ["e", "Exclude"],
      ["u", "Unscreen"],
      ["x / Space", "Toggle selection"],
      ["a", "Select all on page"],
      ["d", "Delete (to trash)"],
    ],
  },
  {
    title: "In a paper",
    items: [
      ["i / m / e / u", "Set decision"],
      ["Tab", "Edit fields"],
      ["Esc", "Close"],
    ],
  },
];

export function HelpOverlay({ open, onClose }: { open: boolean; onClose: () => void }) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div
      className="fixed inset-0 z-[60] flex items-start justify-center overflow-y-auto bg-black/50 p-4 backdrop-blur-sm sm:p-12"
      onClick={onClose}
    >
      <div className="card my-4 w-full max-w-2xl p-6" onClick={(e) => e.stopPropagation()}>
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold">Keyboard shortcuts</h2>
          <button className="text-sm text-[var(--muted)] hover:text-[var(--text)]" onClick={onClose} aria-label="Close">
            ✕
          </button>
        </div>
        <div className="grid gap-6 sm:grid-cols-2">
          {GROUPS.map((g) => (
            <div key={g.title}>
              <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--muted)]">{g.title}</div>
              <div className="space-y-1.5">
                {g.items.map(([k, label]) => (
                  <div key={k} className="flex items-center justify-between gap-3 text-sm">
                    <span className="text-[var(--muted)]">{label}</span>
                    <Kbd>{k}</Kbd>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
