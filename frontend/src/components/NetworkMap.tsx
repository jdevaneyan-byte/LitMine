"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import dynamic from "next/dynamic";
import SpriteText from "three-spritetext";
import { getNetwork } from "@/lib/api";
import type { GraphNode, Network, NetworkFilters, NetworkMode } from "@/lib/types";

// 3D force graph; loose props so our own node/link shapes drive rendering.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const ForceGraph3D = dynamic(() => import("react-force-graph-3d"), { ssr: false }) as any;

const MODES: { key: NetworkMode; label: string; purpose: string }[] = [
  {
    key: "citation",
    label: "Citation",
    purpose:
      "Paper → paper, from what your collected works cite. Bigger nodes are cited by more of your papers; colour runs old → new. Click to open in the Library.",
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
  z?: number;
}
interface FLink {
  source: string | FNode;
  target: string | FNode;
  type?: string;
}
function endId(x: string | FNode): string {
  return typeof x === "object" ? x.id : x;
}
function ekey(a: string, b: string): string {
  return a < b ? `${a}|${b}` : `${b}|${a}`;
}

// Each step of a click-trail gets its own colour, so you can read the order you
// walked the graph (1st click → last click).
const TRAIL_COLORS = [
  "#ef4444", "#f97316", "#eab308", "#22c55e", "#06b6d4",
  "#3b82f6", "#8b5cf6", "#ec4899", "#14b8a6", "#a16207",
];
const ROAD_COLOR = "#f59e0b";
function trailColor(i: number): string {
  return TRAIL_COLORS[i % TRAIL_COLORS.length];
}

// Old → new as a blue→amber ramp for the citation graph's temporal structure.
function yearColor(year: number | null | undefined, min: number, max: number): string {
  if (!year || max <= min) return "#94a3b8";
  const t = Math.max(0, Math.min(1, (year - min) / (max - min)));
  const a = [37, 99, 235];
  const b = [245, 158, 11];
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
  // Click-trail: ordered visited node ids (first → last). Last is the current
  // selection. Each step is coloured differently; reset via button or right-click.
  const [trail, setTrail] = useState<string[]>([]);
  const selectedId = trail.length ? trail[trail.length - 1] : null;

  const [yearMin, setYearMin] = useState("");
  const [yearMax, setYearMax] = useState("");
  const [includedOnly, setIncludedOnly] = useState(false);
  const [minCit, setMinCit] = useState("");

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const fgRef = useRef<any>(null);
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
    setTrail([]);
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

  // Connected, top-weighted subgraph.
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

  const trailIndex = useMemo(() => new Map(trail.map((id, i) => [id, i])), [trail]);
  // Edges between consecutive trail steps that are actually adjacent = the road.
  const pathEdges = useMemo(() => {
    const s = new Set<string>();
    for (let i = 1; i < trail.length; i++) {
      if (adjacency.get(trail[i - 1])?.has(trail[i])) s.add(ekey(trail[i - 1], trail[i]));
    }
    return s;
  }, [trail, adjacency]);

  const neighbors = useMemo(
    () => (selectedId ? adjacency.get(selectedId) ?? new Set<string>() : new Set<string>()),
    [selectedId, adjacency],
  );
  const selectedNode = selectedId ? nodeById.get(selectedId) : null;
  const ranked = useMemo(() => [...nodes].sort((a, b) => b.weight - a.weight).slice(0, 40), [nodes]);

  const maxWeight = useMemo(() => Math.max(1, ...nodes.map((n) => n.weight)), [nodes]);
  const labeled = useMemo(
    () => new Set([...nodes].sort((a, b) => b.weight - a.weight).slice(0, 12).map((n) => n.id)),
    [nodes],
  );
  const yearSpan = useMemo(() => {
    const ys = nodes.map((n) => n.year).filter((y): y is number => typeof y === "number");
    return ys.length ? { min: Math.min(...ys), max: Math.max(...ys) } : { min: 0, max: 0 };
  }, [nodes]);

  const sizeOf = useCallback((n: GraphNode) => 1 + 18 * (n.weight / maxWeight), [maxWeight]);
  const baseColor = useCallback(
    (n: GraphNode) => (mode === "citation" ? yearColor(n.year, yearSpan.min, yearSpan.max) : TYPE_COLOR[n.type] ?? "#6366f1"),
    [mode, yearSpan],
  );

  const focus = useCallback((n: FNode) => {
    if (!fgRef.current || n.x == null) return;
    const r = Math.hypot(n.x || 1, n.y || 1, n.z || 1) || 1;
    const ratio = 1 + 140 / r;
    fgRef.current.cameraPosition(
      { x: (n.x || 0) * ratio, y: (n.y || 0) * ratio, z: (n.z || 0) * ratio },
      { x: n.x || 0, y: n.y || 0, z: n.z || 0 },
      800,
    );
  }, []);

  const visit = useCallback((id: string) => {
    setTrail((t) => (t[t.length - 1] === id ? t : [...t, id]));
  }, []);
  const resetTrail = useCallback(() => setTrail([]), []);

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
          <input className="input w-16 px-2 py-1 text-xs" placeholder="From" value={yearMin} onChange={(e) => setYearMin(e.target.value.replace(/\D/g, ""))} />
          <span>–</span>
          <input className="input w-16 px-2 py-1 text-xs" placeholder="To" value={yearMax} onChange={(e) => setYearMax(e.target.value.replace(/\D/g, ""))} />
        </div>
        <input className="input w-28 px-2 py-1 text-xs" placeholder="Min citations" value={minCit} onChange={(e) => setMinCit(e.target.value.replace(/\D/g, ""))} />
        <label className="flex items-center gap-1.5 text-xs text-[var(--muted)]">
          <input type="checkbox" checked={includedOnly} onChange={(e) => setIncludedOnly(e.target.checked)} />
          Included only
        </label>
        <label className="flex items-center gap-2 text-xs text-[var(--muted)]">
          Nodes
          <input type="range" min={40} max={400} step={10} value={maxNodes} onChange={(e) => setMaxNodes(Number(e.target.value))} />
          <span className="tabular-nums">{maxNodes}</span>
        </label>
        <button className="btn px-2 py-1 text-xs" onClick={resetTrail} disabled={trail.length === 0} title="Clear the click-trail (or right-click the graph)">
          Reset trail
        </button>
        {net && (
          <span className="ml-auto text-xs text-[var(--muted)]">
            {nodes.length} nodes · {links.length} edges{net.stats?.truncated ? " · capped" : ""}
          </span>
        )}
      </div>

      <div className="mb-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-[var(--muted)]">
        <span>{MODES.find((m) => m.key === mode)?.purpose}</span>
        {mode === "citation" && yearSpan.max > yearSpan.min && (
          <span className="flex items-center gap-1.5">
            <span className="tabular-nums">{yearSpan.min}</span>
            <span className="h-2 w-20 rounded-full" style={{ background: "linear-gradient(90deg, rgb(37,99,235), rgb(245,158,11))" }} />
            <span className="tabular-nums">{yearSpan.max}</span>
          </span>
        )}
      </div>

      {/* Click-trail breadcrumb */}
      {trail.length > 0 && (
        <div className="mb-3 flex flex-wrap items-center gap-1 rounded-lg border bg-[var(--surface)] px-3 py-2 text-xs">
          <span className="mr-1 font-semibold uppercase tracking-wide text-[var(--muted)]">Trail:</span>
          {trail.map((id, i) => {
            const n = nodeById.get(id);
            return (
              <span key={`${id}-${i}`} className="flex items-center gap-1">
                {i > 0 && <span className="text-[var(--muted)]">→</span>}
                <button
                  onClick={() => {
                    const node = nodes.find((x) => x.id === id);
                    if (node) focus(node);
                  }}
                  className="flex max-w-[180px] items-center gap-1 truncate rounded px-1.5 py-0.5 hover:bg-[var(--surface-2)]"
                  title={n?.label}
                >
                  <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: trailColor(i) }} />
                  <span className="truncate">{n?.label ?? id}</span>
                </button>
              </span>
            );
          })}
        </div>
      )}

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
                  visit(n.id);
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

        {/* Center: 3D graph */}
        <div ref={wrapRef} className="card relative min-h-[420px] overflow-hidden" style={{ height: "78vh" }}>
          {loading && <div className="absolute inset-0 z-10 flex items-center justify-center text-sm text-[var(--muted)]">Building graph…</div>}
          {error && <div className="absolute inset-0 z-10 flex items-center justify-center px-6 text-center text-sm text-[#b91c1c]">{error}</div>}
          {!loading && !error && nodes.length === 0 && (
            <div className="absolute inset-0 z-10 flex items-center justify-center px-6 text-center text-sm text-[var(--muted)]">
              No connections to show. Try widening the filters, or collect more references.
            </div>
          )}
          <div className="pointer-events-none absolute bottom-2 left-2 z-10 rounded bg-black/40 px-2 py-1 text-[10px] text-white">
            click: add to trail · right-click: reset · drag: rotate · scroll: zoom
          </div>
          {!error && nodes.length > 0 && (
            <ForceGraph3D
              ref={fgRef}
              width={dims.w}
              height={dims.h}
              graphData={{ nodes, links }}
              backgroundColor="#0b1020"
              showNavInfo={false}
              nodeVal={(n: FNode) => sizeOf(n)}
              nodeLabel={(n: FNode) => `${n.label}${n.year ? ` (${n.year})` : ""}`}
              nodeColor={(n: FNode) => {
                if (trailIndex.has(n.id)) return trailColor(trailIndex.get(n.id)!);
                if (trail.length && !neighbors.has(n.id)) return "rgba(150,160,180,0.25)";
                return baseColor(n);
              }}
              nodeOpacity={0.92}
              nodeThreeObjectExtend
              nodeThreeObject={(n: FNode) => {
                const show = trailIndex.has(n.id) || labeled.has(n.id);
                if (!show) return undefined;
                const s = new SpriteText((n.label || "").slice(0, 36));
                s.color = trailIndex.has(n.id) ? trailColor(trailIndex.get(n.id)!) : "#cbd5e1";
                s.textHeight = trailIndex.has(n.id) ? 6 : 4;
                // Lift the label above the sphere.
                // @ts-expect-error three Sprite has position
                s.position.set(0, sizeOf(n) + 6, 0);
                return s;
              }}
              linkColor={(l: FLink) => {
                if (pathEdges.has(ekey(endId(l.source), endId(l.target)))) return ROAD_COLOR;
                if (selectedId && (endId(l.source) === selectedId || endId(l.target) === selectedId)) return "rgba(165,180,252,0.7)";
                return "rgba(140,150,180,0.15)";
              }}
              linkWidth={(l: FLink) => (pathEdges.has(ekey(endId(l.source), endId(l.target))) ? 2.5 : 0.4)}
              linkDirectionalParticles={(l: FLink) => (pathEdges.has(ekey(endId(l.source), endId(l.target))) ? 3 : 0)}
              linkDirectionalParticleWidth={2}
              onNodeClick={(n: FNode) => {
                visit(n.id);
                focus(n);
              }}
              onNodeRightClick={() => resetTrail()}
              onBackgroundRightClick={() => resetTrail()}
            />
          )}
        </div>

        {/* Right: selection detail */}
        <div className="card max-h-[78vh] overflow-y-auto p-3">
          {!selectedNode ? (
            <div className="text-xs text-[var(--muted)]">
              Click a node to start a trail. Each click adds a coloured step; right-click the graph (or Reset trail) to clear.
            </div>
          ) : (
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <span className="h-3 w-3 shrink-0 rounded-full" style={{ background: trailColor((trailIndex.get(selectedId!) ?? 0)) }} />
                <span className="text-[10px] uppercase tracking-wide text-[var(--muted)]">Step {(trailIndex.get(selectedId!) ?? 0) + 1} of {trail.length}</span>
              </div>
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
                <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-[var(--muted)]">Connections — click to extend the trail</div>
                <div className="space-y-1">
                  {[...neighbors]
                    .map((id) => nodeById.get(id))
                    .filter((n): n is GraphNode => Boolean(n))
                    .sort((a, b) => b.weight - a.weight)
                    .slice(0, 30)
                    .map((n) => (
                      <button
                        key={n.id}
                        onClick={() => {
                          visit(n.id);
                          const node = nodes.find((x) => x.id === n.id);
                          if (node) focus(node);
                        }}
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
