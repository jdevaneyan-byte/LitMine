"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import dynamic from "next/dynamic";
import { getNetwork } from "@/lib/api";
import type { GraphNode, Network, NetworkMode } from "@/lib/types";

const ForceGraph3D = dynamic(() => import("react-force-graph-3d"), { ssr: false });

const MODES: { key: NetworkMode; label: string; purpose: string }[] = [
  { key: "citation", label: "Citation", purpose: "Find foundational papers: which works your source papers cite most, and which sources cite them." },
  { key: "author", label: "Authors", purpose: "See the research community: who publishes together on this topic." },
  { key: "journal", label: "Journals", purpose: "See where the field lives: which journals cite which venues." },
];

const TYPE_COLOR: Record<string, string> = {
  review: "#a5b4fc",
  "review-ref": "#38bdf8",
  paper: "#7dd3fc",
  author: "#4ade80",
  journal: "#fbbf24",
};
const DIM = "rgba(120,130,150,0.12)";
const SELECTED_COLOR = "#ffffff";
const ROAD_COLOR = "#f59e0b"; // amber "road" for the path you've travelled

function ekey(a: string, b: string): string {
  return a < b ? `${a}|${b}` : `${b}|${a}`;
}

interface FGNode extends GraphNode {
  raw: GraphNode;
}
interface FGLink {
  source: string | { id: string };
  target: string | { id: string };
  type?: string;
}

function endId(x: string | { id: string }): string {
  return typeof x === "object" ? x.id : x;
}

export default function NetworkMap({ projectId }: { projectId: number }) {
  const [mode, setMode] = useState<NetworkMode>("citation");
  const [net, setNet] = useState<Network | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [maxNodes, setMaxNodes] = useState(120);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  // Persistent "road": nodes visited and edges travelled, in order.
  const [trail, setTrail] = useState<string[]>([]);
  const [pathNodes, setPathNodes] = useState<Set<string>>(new Set());
  const [pathEdges, setPathEdges] = useState<Set<string>>(new Set());

  const fgRef = useRef<{ cameraPosition: (p: object, t: object, ms: number) => void; zoomToFit: (ms?: number, px?: number) => void } | null>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const [dims, setDims] = useState({ w: 800, h: 680 });

  useEffect(() => {
    if (!wrapRef.current) return;
    const ro = new ResizeObserver((entries) => {
      const r = entries[0].contentRect;
      setDims({ w: Math.max(320, r.width), h: Math.max(360, r.height) });
    });
    ro.observe(wrapRef.current);
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    setLoading(true);
    setError(null);
    setSelectedId(null);
    setTrail([]);
    setPathNodes(new Set());
    setPathEdges(new Set());
    getNetwork(projectId, mode)
      .then(setNet)
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [projectId, mode]);

  // Build a connected subgraph + adjacency map.
  const { nodes, links, adjacency, nodeById } = useMemo(() => {
    const empty = { nodes: [] as FGNode[], links: [] as FGLink[], adjacency: new Map<string, Set<string>>(), nodeById: new Map<string, GraphNode>() };
    if (!net) return empty;

    const byId = new Map(net.nodes.map((n) => [n.id, n]));
    let keepIds = new Set<string>();

    if (mode === "citation") {
      // Keep the most-cited papers AND every review that cites them, so the
      // bipartite review→paper edges survive (this is what was broken).
      const papers = net.nodes.filter((n) => n.type !== "review").sort((a, b) => b.weight - a.weight);
      const keptPapers = papers.slice(0, maxNodes).map((p) => p.id);
      const keptPaperSet = new Set(keptPapers);
      const reviewIds = new Set<string>();
      net.edges.forEach((e) => {
        if (keptPaperSet.has(e.target)) reviewIds.add(e.source);
        if (keptPaperSet.has(e.source)) reviewIds.add(e.target);
      });
      keepIds = new Set([...keptPapers, ...reviewIds]);
    } else {
      keepIds = new Set([...net.nodes].sort((a, b) => b.weight - a.weight).slice(0, maxNodes).map((n) => n.id));
    }

    const adj = new Map<string, Set<string>>();
    const flinks: FGLink[] = [];
    net.edges.forEach((e) => {
      if (keepIds.has(e.source) && keepIds.has(e.target)) {
        flinks.push({ source: e.source, target: e.target, type: e.type });
        if (!adj.has(e.source)) adj.set(e.source, new Set());
        if (!adj.has(e.target)) adj.set(e.target, new Set());
        adj.get(e.source)!.add(e.target);
        adj.get(e.target)!.add(e.source);
      }
    });

    // Drop nodes with no connection (keeps the canvas clean).
    const connected = [...keepIds].filter((id) => (adj.get(id)?.size ?? 0) > 0);
    const present = new Set(connected);
    const fnodes: FGNode[] = connected
      .map((id) => byId.get(id)!)
      .filter(Boolean)
      .map((n) => ({ ...n, raw: n }));
    const finalLinks = flinks.filter((l) => present.has(endId(l.source)) && present.has(endId(l.target)));
    return { nodes: fnodes, links: finalLinks, adjacency: adj, nodeById: byId };
  }, [net, mode, maxNodes]);

  const focusCamera = useCallback(
    (id: string) => {
      const node = nodes.find((n) => n.id === id) as unknown as { x?: number; y?: number; z?: number };
      if (node?.x != null && fgRef.current) {
        const r = Math.hypot(node.x || 1, node.y || 1, node.z || 1);
        const ratio = 1 + 160 / (r || 1);
        fgRef.current.cameraPosition(
          { x: (node.x || 0) * ratio, y: (node.y || 0) * ratio, z: (node.z || 0) * ratio },
          { x: node.x || 0, y: node.y || 0, z: node.z || 0 },
          800,
        );
      }
    },
    [nodes],
  );

  // Move focus to a node. If we step to a node adjacent to where we were, the
  // edge between them becomes part of the persistent "road".
  const selectNode = useCallback(
    (id: string | null) => {
      if (id == null) {
        setSelectedId(null);
        return;
      }
      setSelectedId((from) => {
        if (from && from !== id && adjacency.get(from)?.has(id)) {
          setPathEdges((prev) => new Set(prev).add(ekey(from, id)));
        }
        setPathNodes((prev) => {
          const next = new Set(prev);
          if (from) next.add(from);
          next.add(id);
          return next;
        });
        setTrail((prev) => (prev[prev.length - 1] === id ? prev : [...prev, id]));
        return id;
      });
      focusCamera(id);
    },
    [adjacency, focusCamera],
  );

  const resetTrail = useCallback(() => {
    setSelectedId(null);
    setTrail([]);
    setPathNodes(new Set());
    setPathEdges(new Set());
  }, []);

  const active = selectedId != null || pathNodes.size > 0;
  const currentNeighbors = useMemo(
    () => (selectedId ? adjacency.get(selectedId) ?? new Set<string>() : new Set<string>()),
    [selectedId, adjacency],
  );
  const neighborList = useMemo(() => {
    if (!selectedId) return [];
    const ids = [...(adjacency.get(selectedId) ?? [])];
    return ids
      .map((id) => nodeById.get(id))
      .filter((n): n is GraphNode => Boolean(n))
      .sort((a, b) => b.weight - a.weight);
  }, [selectedId, adjacency, nodeById]);

  const selectedNode = selectedId ? nodeById.get(selectedId) : null;

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
        <label className="flex items-center gap-2 text-xs text-[var(--muted)]">
          Max papers
          <input type="range" min={40} max={400} step={20} value={maxNodes} onChange={(e) => setMaxNodes(Number(e.target.value))} />
          <span className="tabular-nums">{maxNodes}</span>
        </label>
        <button
          className="btn"
          onClick={resetTrail}
          disabled={trail.length === 0 && !selectedId}
          title="Clear the path you've travelled"
        >
          Reset trail
        </button>
        {net && (
          <span className="ml-auto text-xs text-[var(--muted)]">
            {nodes.length} nodes · {links.length} edges
          </span>
        )}
      </div>
      <p className="mb-2 text-xs text-[var(--muted)]">{MODES.find((m) => m.key === mode)?.purpose}</p>

      {trail.length > 0 && (
        <div className="mb-3 flex flex-wrap items-center gap-1 rounded-lg border bg-[var(--surface)] px-3 py-2 text-xs">
          <span className="mr-1 font-semibold uppercase tracking-wide text-[var(--muted)]">Trail:</span>
          {trail.map((id, i) => {
            const n = nodeById.get(id);
            return (
              <span key={`${id}-${i}`} className="flex items-center gap-1">
                {i > 0 && <span className="text-[var(--muted)]">→</span>}
                <button
                  onClick={() => selectNode(id)}
                  className={`max-w-[180px] truncate rounded px-1.5 py-0.5 ${
                    id === selectedId ? "bg-[var(--primary-weak)] font-medium text-[var(--primary)]" : "hover:bg-[var(--surface-2)]"
                  }`}
                  title={n?.label}
                >
                  {n?.label ?? id}
                </button>
              </span>
            );
          })}
        </div>
      )}

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-[230px_minmax(0,1fr)_320px]">
        {/* Left: ranked list */}
        <div className="card flex max-h-[80vh] flex-col overflow-hidden">
          <div className="border-b p-2 text-xs font-semibold uppercase tracking-wide text-[var(--muted)]">
            {mode === "citation" ? "Most-cited papers" : mode === "author" ? "Top authors" : "Top journals"}
          </div>
          <div className="flex-1 overflow-y-auto">
            {net &&
              [...net.nodes]
                .filter((n) => (mode === "citation" ? n.type !== "review" : true))
                .sort((a, b) => b.weight - a.weight)
                .slice(0, 120)
                .map((n) => (
                  <button
                    key={n.id}
                    onClick={() => selectNode(n.id)}
                    className={`block w-full border-b px-3 py-2 text-left text-xs transition hover:bg-[var(--surface-2)] ${
                      selectedId === n.id ? "bg-[var(--primary-weak)]" : ""
                    }`}
                  >
                    <div className="line-clamp-2 font-medium">{n.label}</div>
                    <div className="mt-0.5 text-[var(--muted)]">
                      {n.cited_by_count != null ? `cited by ${n.cited_by_count}` : n.papers != null ? `${n.papers} papers` : n.type}
                    </div>
                  </button>
                ))}
          </div>
        </div>

        {/* Middle: 3D graph */}
        <div ref={wrapRef} className="relative h-[80vh] overflow-hidden rounded-[14px] border" style={{ background: "#0b1220" }}>
          {loading && <Overlay text="Building 3D network…" />}
          {error && <Overlay text={error} danger />}
          {!loading && net && nodes.length === 0 && (
            <Overlay text="No connected nodes for this mode. Try increasing Max papers, or switch mode (Authors usually has data)." />
          )}
          {!loading && !error && nodes.length > 0 && (
            <ForceGraph3D
              ref={fgRef as never}
              width={dims.w}
              height={dims.h}
              graphData={{ nodes, links } as never}
              backgroundColor="#0b1220"
              nodeLabel={(n: object) => {
                const node = n as FGNode;
                const extra = node.cited_by_count != null ? ` — cited by ${node.cited_by_count}` : node.papers != null ? ` — ${node.papers} papers` : "";
                return `${node.label}${extra}`;
              }}
              nodeColor={(n: object) => {
                const node = n as FGNode;
                if (!active) return TYPE_COLOR[node.type] ?? "#94a3b8";
                if (node.id === selectedId) return SELECTED_COLOR;
                if (currentNeighbors.has(node.id)) return TYPE_COLOR[node.type] ?? "#94a3b8";
                if (pathNodes.has(node.id)) return ROAD_COLOR; // visited — part of the road
                return DIM;
              }}
              nodeVal={(n: object) => {
                const node = n as FGNode;
                const base = 1 + Math.min(30, node.weight);
                if (node.id === selectedId) return base * 1.9;
                if (pathNodes.has(node.id)) return base * 1.3;
                return base;
              }}
              nodeOpacity={1}
              nodeResolution={14}
              linkColor={(l: object) => {
                const link = l as FGLink;
                const s = endId(link.source);
                const t = endId(link.target);
                if (pathEdges.has(ekey(s, t))) return ROAD_COLOR; // the road persists
                if (active && (s === selectedId || t === selectedId)) return "rgba(165,180,252,0.95)";
                if (active) return "rgba(80,90,110,0.05)";
                return "rgba(148,163,184,0.22)";
              }}
              linkWidth={(l: object) => {
                const link = l as FGLink;
                const s = endId(link.source);
                const t = endId(link.target);
                if (pathEdges.has(ekey(s, t))) return 2.6; // road is the boldest
                return active && (s === selectedId || t === selectedId) ? 1.4 : 0.4;
              }}
              warmupTicks={50}
              cooldownTicks={90}
              onNodeClick={(n: object) => selectNode((n as FGNode).id)}
              onBackgroundClick={() => selectNode(null)}
              enableNodeDrag={false}
            />
          )}
          <div className="pointer-events-none absolute bottom-2 left-3 text-[10px] text-slate-400">
            drag to rotate · scroll to zoom · click a node to focus its links
          </div>
        </div>

        {/* Right: focused node + its connections */}
        <div className="card max-h-[80vh] overflow-y-auto p-4">
          {selectedNode ? (
            <div>
              <span className="badge" style={{ background: (TYPE_COLOR[selectedNode.type] ?? "#94a3b8") + "33", color: "#334155" }}>
                {selectedNode.type}
              </span>
              <h3 className="mt-2 text-sm font-semibold leading-snug">{selectedNode.label}</h3>
              <dl className="mt-3 space-y-1.5 text-xs">
                {selectedNode.year != null && <Row k="Year" v={String(selectedNode.year)} />}
                {selectedNode.cited_by_count != null && <Row k="Cited by (sources)" v={String(selectedNode.cited_by_count)} />}
                {selectedNode.papers != null && <Row k="Papers" v={String(selectedNode.papers)} />}
                {selectedNode.doi && (
                  <Row k="DOI" v={<a className="text-[var(--primary)] hover:underline" href={`https://doi.org/${selectedNode.doi}`} target="_blank" rel="noreferrer">{selectedNode.doi}</a>} />
                )}
              </dl>

              <div className="mt-4 border-t pt-3">
                <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--muted)]">
                  Connected to ({neighborList.length})
                </div>
                <div className="space-y-1">
                  {neighborList.slice(0, 60).map((n) => (
                    <button
                      key={n.id}
                      onClick={() => selectNode(n.id)}
                      className="block w-full rounded-md px-2 py-1.5 text-left text-xs transition hover:bg-[var(--surface-2)]"
                    >
                      <span
                        className="mr-1.5 inline-block h-2 w-2 rounded-full align-middle"
                        style={{ background: TYPE_COLOR[n.type] ?? "#94a3b8" }}
                      />
                      <span className="line-clamp-1 align-middle">{n.label}</span>
                    </button>
                  ))}
                  {neighborList.length === 0 && <div className="text-xs text-[var(--muted)]">No connections in view.</div>}
                </div>
              </div>
            </div>
          ) : (
            <div className="grid h-full place-items-center px-2 text-center text-xs text-[var(--muted)]">
              Click a node — its connections light up here and in the graph, so you can trace what links to what.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function Overlay({ text, danger }: { text: string; danger?: boolean }) {
  return (
    <div className={`absolute inset-0 z-10 grid place-items-center p-6 text-center text-sm ${danger ? "text-red-300" : "text-slate-300"}`}>
      {text}
    </div>
  );
}

function Row({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-3">
      <dt className="text-[var(--muted)]">{k}</dt>
      <dd className="text-right">{v}</dd>
    </div>
  );
}
