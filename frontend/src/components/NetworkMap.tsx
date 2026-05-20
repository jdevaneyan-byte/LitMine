"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import dynamic from "next/dynamic";
import { getNetwork } from "@/lib/api";
import type { GraphEdge, GraphNode, Network, NetworkMode } from "@/lib/types";

// react-force-graph-3d uses three.js (needs window) → load client-only.
const ForceGraph3D = dynamic(() => import("react-force-graph-3d"), { ssr: false });

const MODES: { key: NetworkMode; label: string; hint: string }[] = [
  { key: "citation", label: "Citation", hint: "Reviews → the papers they cite. Bigger = cited by more reviews." },
  { key: "author", label: "Authors", hint: "Authors linked when they share a paper. Bigger = more papers." },
  { key: "journal", label: "Journals", hint: "A review's journal → the venues of the papers it cites." },
];

const TYPE_COLOR: Record<string, string> = {
  review: "#a5b4fc",
  "review-ref": "#38bdf8",
  paper: "#7dd3fc",
  author: "#4ade80",
  journal: "#fbbf24",
};

interface FGNode extends GraphNode {
  raw: GraphNode;
  degree: number;
}

export default function NetworkMap({ projectId }: { projectId: number }) {
  const [mode, setMode] = useState<NetworkMode>("citation");
  const [net, setNet] = useState<Network | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<GraphNode | null>(null);
  const [maxNodes, setMaxNodes] = useState(150);
  const [hideIsolated, setHideIsolated] = useState(true);

  const graphRef = useRef<{ cameraPosition: (p: object, t: object, ms: number) => void } | null>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const [dims, setDims] = useState({ w: 800, h: 640 });

  // Measure the graph container so the canvas fills it.
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
    setSelected(null);
    getNetwork(projectId, mode)
      .then(setNet)
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [projectId, mode]);

  // Filter to the top-`maxNodes` by weight, keep only internal edges, then
  // (optionally) drop nodes left with no connections — that removes the
  // ugly grid of disconnected dots.
  const graphData = useMemo(() => {
    if (!net) return { nodes: [] as FGNode[], links: [] as GraphEdge[] };
    const top = [...net.nodes].sort((a, b) => b.weight - a.weight).slice(0, maxNodes);
    const keep = new Set(top.map((n) => n.id));
    const links = net.edges.filter((e) => keep.has(e.source) && keep.has(e.target));
    const degree = new Map<string, number>();
    links.forEach((l) => {
      degree.set(l.source, (degree.get(l.source) ?? 0) + 1);
      degree.set(l.target, (degree.get(l.target) ?? 0) + 1);
    });
    let nodes: FGNode[] = top.map((n) => ({ ...n, raw: n, degree: degree.get(n.id) ?? 0 }));
    if (hideIsolated) nodes = nodes.filter((n) => n.degree > 0);
    const present = new Set(nodes.map((n) => n.id));
    const finalLinks = links.filter((l) => present.has(l.source) && present.has(l.target));
    return { nodes, links: finalLinks.map((l) => ({ ...l })) };
  }, [net, maxNodes, hideIsolated]);

  const focusNode = useCallback((n: GraphNode) => {
    setSelected(n);
    const node = graphData.nodes.find((x) => x.id === n.id) as unknown as { x?: number; y?: number; z?: number };
    if (node?.x != null && graphRef.current) {
      const dist = 120;
      const ratio = 1 + dist / Math.hypot(node.x || 1, node.y || 1, node.z || 1);
      graphRef.current.cameraPosition(
        { x: (node.x || 0) * ratio, y: (node.y || 0) * ratio, z: (node.z || 0) * ratio },
        { x: node.x || 0, y: node.y || 0, z: node.z || 0 },
        800,
      );
    }
  }, [graphData]);

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
          Max nodes
          <input
            type="range"
            min={50}
            max={Math.min(800, net?.nodes.length ?? 800)}
            step={25}
            value={maxNodes}
            onChange={(e) => setMaxNodes(Number(e.target.value))}
          />
          <span className="tabular-nums">{maxNodes}</span>
        </label>

        <label className="flex items-center gap-1.5 text-xs text-[var(--muted)]">
          <input type="checkbox" checked={hideIsolated} onChange={(e) => setHideIsolated(e.target.checked)} />
          Hide disconnected
        </label>

        <span className="hidden text-xs text-[var(--muted)] lg:inline">{MODES.find((m) => m.key === mode)?.hint}</span>
        {net && (
          <span className="ml-auto text-xs text-[var(--muted)]">
            showing {graphData.nodes.length} / {net.nodes.length} nodes · {graphData.links.length} edges
          </span>
        )}
      </div>

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-[240px_minmax(0,1fr)_300px]">
        {/* Left: top-nodes list, pinned left */}
        <div className="card flex max-h-[80vh] flex-col overflow-hidden">
          <div className="border-b p-2 text-xs font-semibold uppercase tracking-wide text-[var(--muted)]">
            Top nodes
          </div>
          <div className="flex-1 overflow-y-auto">
            {net &&
              [...net.nodes]
                .sort((a, b) => b.weight - a.weight)
                .slice(0, 120)
                .map((n) => (
                  <button
                    key={n.id}
                    onClick={() => focusNode(n)}
                    className={`block w-full border-b px-3 py-2 text-left text-xs transition hover:bg-[var(--surface-2)] ${
                      selected?.id === n.id ? "bg-[var(--primary-weak)]" : ""
                    }`}
                  >
                    <div className="line-clamp-2 font-medium">{n.label}</div>
                    <div className="mt-0.5 text-[var(--muted)]">
                      {n.cited_by_count != null
                        ? `cited by ${n.cited_by_count}`
                        : n.papers != null
                        ? `${n.papers} papers`
                        : n.type}
                    </div>
                  </button>
                ))}
          </div>
        </div>

        {/* Middle: big 3D graph */}
        <div
          ref={wrapRef}
          className="relative h-[80vh] overflow-hidden rounded-[14px] border"
          style={{ background: "#0b1220" }}
        >
          {loading && (
            <div className="absolute inset-0 z-10 grid place-items-center text-sm text-slate-300">
              Building 3D network…
            </div>
          )}
          {error && (
            <div className="absolute inset-0 z-10 grid place-items-center p-6 text-center text-sm text-red-300">
              {error}
            </div>
          )}
          {!loading && net && graphData.nodes.length === 0 && (
            <div className="absolute inset-0 z-10 grid place-items-center p-6 text-center text-sm text-slate-300">
              No connected nodes for this mode. Citation needs extracted references; try unchecking
              “Hide disconnected” or another mode.
            </div>
          )}
          {!loading && !error && graphData.nodes.length > 0 && (
            <ForceGraph3D
              ref={graphRef as never}
              width={dims.w}
              height={dims.h}
              graphData={graphData as never}
              backgroundColor="#0b1220"
              nodeLabel={(n: object) => {
                const node = n as FGNode;
                const extra = node.cited_by_count != null ? ` — cited by ${node.cited_by_count}` : node.papers != null ? ` — ${node.papers} papers` : "";
                return `${node.label}${extra}`;
              }}
              nodeColor={(n: object) => TYPE_COLOR[(n as FGNode).type] ?? "#94a3b8"}
              nodeVal={(n: object) => 1 + Math.min(30, (n as FGNode).weight)}
              nodeOpacity={0.92}
              nodeResolution={12}
              linkColor={() => "rgba(148,163,184,0.25)"}
              linkWidth={0.4}
              linkDirectionalParticles={0}
              warmupTicks={40}
              cooldownTicks={80}
              onNodeClick={(n: object) => focusNode((n as FGNode).raw)}
              enableNodeDrag={false}
            />
          )}
        </div>

        {/* Right: details, pinned right */}
        <div className="card max-h-[80vh] overflow-y-auto p-4">
          {selected ? (
            <div>
              <span
                className="badge"
                style={{ background: (TYPE_COLOR[selected.type] ?? "#94a3b8") + "33", color: "#334155" }}
              >
                {selected.type}
              </span>
              <h3 className="mt-2 text-sm font-semibold leading-snug">{selected.label}</h3>
              <dl className="mt-3 space-y-1.5 text-xs">
                {selected.year != null && <Row k="Year" v={String(selected.year)} />}
                {selected.cited_by_count != null && <Row k="Cited by (reviews)" v={String(selected.cited_by_count)} />}
                {selected.papers != null && <Row k="Papers" v={String(selected.papers)} />}
                {selected.doi && (
                  <Row
                    k="DOI"
                    v={
                      <a className="text-[var(--primary)] hover:underline" href={`https://doi.org/${selected.doi}`} target="_blank" rel="noreferrer">
                        {selected.doi}
                      </a>
                    }
                  />
                )}
              </dl>
            </div>
          ) : (
            <div className="grid h-full place-items-center text-center text-xs text-[var(--muted)]">
              Click a node (or a top-node on the left) to focus it and see details.
            </div>
          )}
        </div>
      </div>
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
