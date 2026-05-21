"use client";

import { useEffect, useMemo, useRef, useState } from "react";

export interface Command {
  id: string;
  label: string;
  hint?: string;
  group?: string;
  run: () => void;
}

export default function CommandPalette({
  open,
  commands,
  onSearch,
  onClose,
}: {
  open: boolean;
  commands: Command[];
  onSearch?: (q: string) => Promise<Command[]>;
  onClose: () => void;
}) {
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const [dynamic, setDynamic] = useState<Command[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open) {
      setQuery("");
      setActive(0);
      setDynamic([]);
      setTimeout(() => inputRef.current?.focus(), 0);
    }
  }, [open]);

  // Live article search (debounced) via the provided provider.
  useEffect(() => {
    if (!onSearch) return;
    const q = query.trim();
    if (q.length < 2) {
      setDynamic([]);
      return;
    }
    const h = setTimeout(() => {
      onSearch(q).then(setDynamic).catch(() => setDynamic([]));
    }, 200);
    return () => clearTimeout(h);
  }, [query, onSearch]);

  const staticFiltered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return commands;
    return commands.filter((c) => (c.label + " " + (c.group ?? "")).toLowerCase().includes(q));
  }, [query, commands]);

  const filtered = useMemo(() => [...staticFiltered, ...dynamic], [staticFiltered, dynamic]);

  useEffect(() => {
    setActive((a) => Math.min(a, Math.max(0, filtered.length - 1)));
  }, [filtered.length]);

  if (!open) return null;

  const run = (c?: Command) => {
    if (!c) return;
    onClose();
    c.run();
  };

  return (
    <div
      className="fixed inset-0 z-[60] flex items-start justify-center bg-black/50 p-4 pt-[12vh] backdrop-blur-sm"
      onClick={onClose}
    >
      <div className="card w-full max-w-lg overflow-hidden p-0 shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <input
          ref={inputRef}
          className="w-full border-b bg-transparent px-4 py-3 text-sm outline-none placeholder:text-[var(--muted)]"
          placeholder="Search papers or run a command…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "ArrowDown") {
              e.preventDefault();
              setActive((a) => Math.min(a + 1, filtered.length - 1));
            } else if (e.key === "ArrowUp") {
              e.preventDefault();
              setActive((a) => Math.max(a - 1, 0));
            } else if (e.key === "Enter") {
              e.preventDefault();
              run(filtered[active]);
            } else if (e.key === "Escape") {
              onClose();
            }
          }}
        />
        <div className="max-h-[50vh] overflow-y-auto py-1">
          {filtered.length === 0 && (
            <div className="px-4 py-6 text-center text-sm text-[var(--muted)]">No matching command.</div>
          )}
          {filtered.map((c, i) => (
            <button
              key={c.id}
              onMouseEnter={() => setActive(i)}
              onClick={() => run(c)}
              className={`flex w-full items-center justify-between gap-3 px-4 py-2 text-left text-sm ${
                i === active ? "bg-[var(--primary-weak)] text-[var(--primary)]" : "hover:bg-[var(--surface-2)]"
              }`}
            >
              <span>
                {c.group && <span className="text-[var(--muted)]">{c.group} · </span>}
                {c.label}
              </span>
              {c.hint && <span className="font-mono text-[10px] text-[var(--muted)]">{c.hint}</span>}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
