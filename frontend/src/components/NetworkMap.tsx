"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import dynamic from "next/dynamic";
import { getNetwork } from "@/lib/api";
import type { GraphNode, Network, NetworkFilters, NetworkMode } from "@/lib/types";

// The library's generic prop types fight our own node/link shapes; load it with
// loose props so our typed canvas/link callbacks drive the rendering instead.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const ForceGraph2D = dynamic(() => import("react-force-graph-2d"), { ssr: false }) as any;

const MODES: { key: NetworkMode; label: string; purpose: string }[] = [
  {
    key: "citation",
    label: "Citation",
    purpose:
      "Paper → paper, from what your collected works cite. Bigger nodes are cited by more of your papers — the foundational core. Click a node to open it in the Library.",
  },
  { key: "author", label: "Authors", purpose: "Co-authorship: researchers linked when they share a paper in your set." },
  { key: "journal", label: "Journals", purpose: "Venue → venue: which journals your papers cite which other journals." },
];

const TYPE_COLOR: Record<string, string> = {
  paper: "#6366f1",
  reference: "#0ea5e9",
  author: "#22c55e",
  journal: "#f59e0b",
};

interface FNode extends GraphNode {
  x?: number;
  y?: number;
}
interface FLink {
  source: string | FNode;
  target: string | FNode;
  type?: string;
}
function endId(x: string | FNode): string {
  return typeof x === "object" ? x.id : x;
}

// Old → new as a blue→amber ramp, so the citation graph's temporal structure is
// visible at a glance (foundational older work vs. recent papers).
function yearColor(year: number | null | undefined, min: number, max: number): string {
  if (!year || max <= min) return "#94a3b8";
  const t = Math.max(0, Math.min(1, (year - min) / (max - min)));
  const a = [37, 99, 235]; // #2563eb blue (older)
  const b = [245, 158, 11]; // #f59e0b amber (newer)
  const c = a.map((v, i) => Math.round(v + (b[i] - v) * t));
  return `rgb(${c[0]},${c[1]},${c[2]})`;
}

export default function NetworkMap({
  projectId,
  onOpenPaper,
}: {
  projectId: number;
  onOpenPaper?: (id: number) => void;
}) {
  const [mode, setMode] = useState<NetworkMode>("citation");
  const [net, setNet] = useState<Network | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [maxNodes, setMaxNodes] = useState(150);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  // Filters (applied on change — the backend builder is fast).
  const [yearMin, setYearMin] = useState("");
  const [yearMax, setYearMax] = useState("");
  const [includedOnly, setIncludedOnly] = useState(false);
  const [minCit, setMinCit] = useState("");

  const fgRef = useRef<{ centerAt: (x: number, y: number, ms?: number) => void; zoom: (z: number, ms?: number) => void } | null>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const [dims, setDims] = useState({ w: 800, h: 620 });

  useEffect(() => {
    if (!wrapRef.current) return;
    const ro = new ResizeObserver((entries) => {
      const r = entries[0].contentRect;
      setDims({ w: Math.max(320, r.width), h: Math.max(420, r.height) });
    });
    ro.observe(wrapRef.current);
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    setLoading(true);
    setError(null);
    setSelectedId(null);
    const filters: NetworkFilters = {
      year_min: yearMin ? Number(yearMin) : undefined,
      year_max: yearMax ? Number(yearMax) : undefined,
      included_only: includedOnly || undefined,
      min_citations: minCit ? Number(minCit) : undefined,
    };
    getNetwork(projectId, mode, filters)
      .then(setNet)
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [projectId, mode, yearMin, yearMax, includedOnly, minCit]);

  // Keep the top-weighted, connected subgraph.
  const { nodes, links, adjacency, nodeById } = useMemo(() => {
    const empty = {
      nodes: [] as FNode[],
      links: [] as FLink[],
      adjacency: new Map<string, Set<string>>(),
      nodeById: new Map<string, GraphNode>(),
    };
    if (!net) return empty;
    const byId = new Map(net.nodes.map((n) => [n.id, n]));
    const keep = new Set(
      [...net.nodes].sort((a, b) => b.weight - a.weight).slice(0, maxNodes).map((n) => n.id),
    );
    // Journal flows are extremely dense (every venue cites every other), so keep
    // only the meaningful ones; otherwise the graph is an unreadable hairball.
    const minEdgeWeight = mode === "journal" ? 3 : 1;
    const adj = new Map<string, Set<string>>();
    const flinks: FLink[] = [];
    net.edges.forEach((e) => {
      if ((e.weight ?? 1) < minEdgeWeight) return;
      if (keep.has(e.source) && keep.has(e.target)) {
        flinks.push({ source: e.source, target: e.target, type: e.type });
        if (!adj.has(e.source)) adj.set(e.source, new Set());
        if (!adj.has(e.target)) adj.set(e.target, new Set());
        adj.get(e.source)!.add(e.target);
        adj.get(e.target)!.add(e.source);
      }
    });
    const connected = [...keep].filter((id) => (adj.get(id)?.size ?? 0) > 0);
    const present = new Set(connected);
    const fnodes = connected.map((id) => ({ ...(byId.get(id) as GraphNode) }));
    const finalLinks = flinks.filter((l) => present.has(endId(l.source)) && present.has(endId(l.target)));
    return { nodes: fnodes, links: finalLinks, adjacency: adj, nodeById: byId };
  }, [net, maxNodes, mode]);

  const neighbors = useMemo(
    () => (selectedId ? adjacency.get(selectedId) ?? new Set<string>() : new Set<string>()),
    [selectedId, adjacency],
  );

  const selectedNode = selectedId ? nodeById.get(selectedId) : null;

  const ranked = useMemo(
    () => [...nodes].sort((a, b) => b.weight - a.weight).slice(0, 40),
    [nodes],
  );

  // Only the heaviest nodes carry an always-on label; everything else reveals
  // its label on hover or when you zoom in. This is what keeps the canvas from
  // turning into text soup.
  const maxWeight = useMemo(() => Math.max(1, ...nodes.map((n) => n.weight)), [nodes]);
  const labeled = useMemo(
    () => new Set([...nodes].sort((a, b) => b.weight - a.weight).slice(0, 14).map((n) => n.id)),
    [nodes],
  );
  const yearSpan = useMemo(() => {
    const ys = nodes.map((n) => n.year).filter((y): y is number => typeof y === "number");
    return ys.length ? { min: Math.min(...ys), max: Math.max(...ys) } : { min: 0, max: 0 };
  }, [nodes]);

  // Spread the graph out so clusters separate instead of piling into a blob.
  useEffect(() => {
    const fg = fgRef.current as unknown as {
      d3Force?: (n: string) => { strength: (v: number) => void } | undefined;
      d3ReheatSimulation?: () => void;
    } | null;
    if (fg?.d3Force) {
      fg.d3Force("charge")?.strength(-110);
      fg.d3ReheatSimulation?.();
    }
  }, [nodes]);

  const focus = useCallback((n: FNode) => {
    if (fgRef.current && n.x != null && n.y != null) {
      fgRef.current.centerAt(n.x, n.y, 600);
      fgRef.current.zoom(4, 600);
    }
  }, []);

  // Radius normalized into a tight range so the biggest hub isn't a giant blob.
  const sizeOf = useCallback((n: GraphNode) => 3 + 10 * Math.sqrt(n.weight / maxWeight), [maxWeight]);
  // Citation nodes are colored by year (old → new); others by their kind.
  const colorOf = useCallback(
    (n: GraphNode) => (mode === "citation" ? yearColor(n.year, yearSpan.min, yearSpan.max) : TYPE_COLOR[n.type] ?? "#6366f1"),
    [mode, yearSpan],
  );

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-3">
        <div className="flex gap-1 rounded-lg border p-1">
          {MODES.map((m) => (
            <button
              key={m.key}
              onClick={() => setMode(m.key)}
              className={`rounded-md px-3 py-1.5 text-sm font-medium transition ${
                mode === m.key ? "bg-[var(--primary)] text-white" : "text-[var(--muted)] hover:text-[var(--text)]"
              }`}
            >
              {m.label}
            </button>
          ))}
        </div>

        <div className="flex items-center gap-1 text-xs text-[var(--muted)]" title="Year range">
          <input
            className="input w-16 px-2 py-1 text-xs"
            placeholder="From"
            value={yearMin}
            onChange={(e) => setYearMin(e.target.value.replace(/\D/g, ""))}
          />
          <span>–</span>
          <input
            className="input w-16 px-2 py-1 text-xs"
            placeholder="To"
            value={yearMax}
            onChange={(e) => setYearMax(e.target.value.replace(/\D/g, ""))}
          />
        </div>
        <input
          className="input w-28 px-2 py-1 text-xs"
          placeholder="Min citations"
          value={minCit}
          onChange={(e) => setMinCit(e.target.value.replace(/\D/g, ""))}
        />
        <label className="flex items-center gap-1.5 text-xs text-[var(--muted)]">
          <input type="checkbox" checked={includedOnly} onChange={(e) => setIncludedOnly(e.target.checked)} />
          Included only
        </label>
        <label className="flex items-center gap-2 text-xs text-[var(--muted)]">
          Nodes
          <input type="range" min={40} max={400} step={10} value={maxNodes} onChange={(e) => setMaxNodes(Number(e.target.value))} />
          <span className="tabular-nums">{maxNodes}</span>
        </label>
        {net && (
          <span className="ml-auto text-xs text-[var(--muted)]">
            {nodes.length} nodes · {links.length} edges
            {net.stats?.truncated ? " · capped" : ""}
          </span>
        )}
      </div>
      <div className="mb-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-[var(--muted)]">
        <span>{MODES.find((m) => m.key === mode)?.purpose}</span>
        {mode === "citation" && yearSpan.max > yearSpan.min && (
          <span className="flex items-center gap-1.5">
            <span className="tabular-nums">{yearSpan.min}</span>
            <span
              className="h-2 w-20 rounded-full"
              style={{ background: "linear-gradient(90deg, rgb(37,99,235), rgb(245,158,11))" }}
            />
            <span className="tabular-nums">{yearSpan.max}</span>
          </span>
        )}
      </div>

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-[230px_minmax(0,1fr)_300px]">
        {/* Left: ranked list */}
        <div className="card flex max-h-[78vh] flex-col overflow-hidden">
          <div className="border-b p-2 text-xs font-semibold uppercase tracking-wide text-[var(--muted)]">
            {mode === "citation" ? "Most-cited (your set)" : mode === "author" ? "Top authors" : "Top journals"}
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto">
            {ranked.map((n) => (
              <button
                key={n.id}
                onClick={() => {
                  setSelectedId(n.id);
                  focus(n);
                }}
                className={`block w-full border-b px-2 py-1.5 text-left text-xs last:border-0 hover:bg-[var(--surface-2)] ${
                  selectedId === n.id ? "bg-[var(--primary-weak)]" : ""
                }`}
                title={n.label}
              >
                <span className="line-clamp-2">{n.label}</span>
                <span className="text-[10px] text-[var(--muted)]">
                  {mode === "citation" ? `cited by ${n.cited_by_count ?? 0}` : `${n.papers ?? 0} papers`}
                </span>
              </button>
            ))}
            {ranked.length === 0 && !loading && <div className="p-3 text-xs italic text-[var(--muted)]">No connections.</div>}
          </div>
        </div>

        {/* Center: graph */}
        <div ref={wrapRef} className="card relative min-h-[420px] overflow-hidden" style={{ height: "78vh" }}>
          {loading && <div className="absolute inset-0 z-10 flex items-center justify-center text-sm text-[var(--muted)]">Building graph…</div>}
          {error && <div className="absolute inset-0 z-10 flex items-center justify-center px-6 text-center text-sm text-[#b91c1c]">{error}</div>}
          {!loading && !error && nodes.length === 0 && (
            <div className="absolute inset-0 z-10 flex items-center justify-center px-6 text-center text-sm text-[var(--muted)]">
              No connections to show. Try widening the filters, or collect more references.
            </div>
          )}
          {!error && nodes.length > 0 && (
            <ForceGraph2D
              ref={fgRef as never}
              width={dims.w}
              height={dims.h}
              graphData={{ nodes, links }}
              cooldownTicks={150}
              d3VelocityDecay={0.35}
              nodeLabel={(n: FNode) => `${n.label}${n.year ? ` (${n.year})` : ""}`}
              linkColor={(l: FLink) =>
                selectedId && (endId(l.source) === selectedId || endId(l.target) === selectedId)
                  ? "rgba(99,102,241,0.6)"
                  : "rgba(120,130,150,0.10)"
              }
              linkWidth={(l: FLink) => (selectedId && (endId(l.source) === selectedId || endId(l.target) === selectedId) ? 1.5 : 0.4)}
              linkDirectionalArrowLength={(l: FLink) =>
                (mode === "journal" || mode === "citation") && selectedId && (endId(l.source) === selectedId || endId(l.target) === selectedId) ? 3 : 0
              }
              linkDirectionalArrowRelPos={1}
              onNodeClick={(n: FNode) => {
                setSelectedId(n.id);
                focus(n);
              }}
              onBackgroundClick={() => setSelectedId(null)}
              nodePointerAreaPaint={(n: FNode, color: string, ctx: CanvasRenderingContext2D) => {
                // Hit area must match the drawn circle, or clicks/hover won't register.
                ctx.fillStyle = color;
                ctx.beginPath();
                ctx.arc(n.x ?? 0, n.y ?? 0, sizeOf(n), 0, 2 * Math.PI);
                ctx.fill();
              }}
              nodeCanvasObject={(n: FNode, ctx: CanvasRenderingContext2D, scale: number) => {
                const r = sizeOf(n);
                const sel = n.id === selectedId;
                const dim = !!selectedId && !sel && !neighbors.has(n.id);
                ctx.globalAlpha = dim ? 0.12 : 1;
                ctx.beginPath();
                ctx.arc(n.x ?? 0, n.y ?? 0, r, 0, 2 * Math.PI);
                ctx.fillStyle = sel ? "#111827" : colorOf(n);
                ctx.fill();
                if (sel) {
                  ctx.lineWidth = 1.5 / scale;
                  ctx.strokeStyle = "#111827";
                  ctx.stroke();
                }
                // Show a label only for top nodes, the selection + its neighbors,
                // or once zoomed in — with a white halo so it stays readable.
                const show = !dim && (sel || neighbors.has(n.id) || labeled.has(n.id) || scale > 4.5);
                if (show) {
                  const label = (n.label || "").slice(0, 42);
                  const fs = Math.max(9 / scale, 2.6);
                  ctx.font = `${fs}px sans-serif`;
                  const w = ctx.measureText(label).width;
                  const lx = (n.x ?? 0) + r + 1.5 / scale;
                  const ly = n.y ?? 0;
                  ctx.fillStyle = "rgba(255,255,255,0.82)";
                  ctx.fillRect(lx - 0.5, ly - fs / 2 - 0.5, w + 1, fs + 1);
                  ctx.fillStyle = "#1f2937";
                  ctx.textAlign = "left";
                  ctx.textBaseline = "middle";
                  ctx.fillText(label, lx, ly);
                }
                ctx.globalAlpha = 1;
              }}
            />
          )}
        </div>

        {/* Right: selection detail */}
        <div className="card max-h-[78vh] overflow-y-auto p-3">
          {!selectedNode ? (
            <div className="text-xs text-[var(--muted)]">Click a node to inspect it. Bigger = more cited by your set.</div>
          ) : (
            <div className="space-y-2">
              <div className="text-sm font-semibold leading-snug">{selectedNode.label}</div>
              <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-[var(--muted)]">
                {selectedNode.year != null && <span>{selectedNode.year}</span>}
                {mode === "citation" && <span>cited by {selectedNode.cited_by_count ?? 0} of yours</span>}
                {selectedNode.papers != null && <span>{selectedNode.papers} papers</span>}
                <span>{neighbors.size} connections</span>
              </div>
              {mode === "citation" && selectedNode.article_id != null && onOpenPaper && (
                <button className="btn btn-primary w-full px-2 py-1 text-xs" onClick={() => onOpenPaper(selectedNode.article_id!)}>
                  Open in Library
                </button>
              )}
              <div className="border-t pt-2">
                <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-[var(--muted)]">Connections</div>
                <div className="space-y-1">
                  {[...neighbors]
                    .map((id) => nodeById.get(id))
                    .filter((n): n is GraphNode => Boolean(n))
                    .sort((a, b) => b.weight - a.weight)
                    .slice(0, 30)
                    .map((n) => (
                      <button
                        key={n.id}
                        onClick={() => setSelectedId(n.id)}
                        className="block w-full truncate rounded px-1.5 py-1 text-left text-xs hover:bg-[var(--surface-2)]"
                        title={n.label}
                      >
                        {n.label}
                      </button>
                    ))}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
