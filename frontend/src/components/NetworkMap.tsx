"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import cytoscape, { type Core, type ElementDefinition } from "cytoscape";
// @ts-expect-error - no bundled types for the layout plugin
import fcose from "cytoscape-fcose";
import { getNetwork } from "@/lib/api";
import type { GraphNode, Network, NetworkMode } from "@/lib/types";

cytoscape.use(fcose);

const MODES: { key: NetworkMode; label: string; hint: string }[] = [
  { key: "citation", label: "Citation", hint: "Reviews → the papers they cite. Bigger = cited by more reviews." },
  { key: "author", label: "Authors", hint: "Authors linked when they share a paper. Bigger = more papers." },
  { key: "journal", label: "Journals", hint: "A review's journal → the venue of papers it cites." },
];

const TYPE_COLOR: Record<string, string> = {
  review: "#4f46e5",
  "review-ref": "#0ea5e9",
  paper: "#64748b",
  author: "#16a34a",
  journal: "#d97706",
};

export default function NetworkMap({ projectId }: { projectId: number }) {
  const [mode, setMode] = useState<NetworkMode>("citation");
  const [net, setNet] = useState<Network | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<GraphNode | null>(null);

  const containerRef = useRef<HTMLDivElement>(null);
  const cyRef = useRef<Core | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    setSelected(null);
    getNetwork(projectId, mode)
      .then(setNet)
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [projectId, mode]);

  const elements = useMemo<ElementDefinition[]>(() => {
    if (!net) return [];
    const nodeIds = new Set(net.nodes.map((n) => n.id));
    const els: ElementDefinition[] = net.nodes.map((n) => ({
      data: { id: n.id, label: n.label, type: n.type, weight: n.weight, raw: n },
    }));
    net.edges.forEach((e, i) => {
      if (nodeIds.has(e.source) && nodeIds.has(e.target)) {
        els.push({ data: { id: `e${i}`, source: e.source, target: e.target } });
      }
    });
    return els;
  }, [net]);

  useEffect(() => {
    if (!containerRef.current || !net) return;
    cyRef.current?.destroy();
    const cy = cytoscape({
      container: containerRef.current,
      elements,
      style: [
        {
          selector: "node",
          style: {
            "background-color": (ele: cytoscape.NodeSingular) => TYPE_COLOR[ele.data("type")] ?? "#94a3b8",
            width: (ele: cytoscape.NodeSingular) => 8 + Math.min(40, Number(ele.data("weight")) * 3),
            height: (ele: cytoscape.NodeSingular) => 8 + Math.min(40, Number(ele.data("weight")) * 3),
            label: "",
          },
        },
        {
          selector: "node:selected",
          style: { "border-width": 3, "border-color": "#101828" },
        },
        {
          selector: "edge",
          style: {
            width: 1,
            "line-color": "#d0d5dd",
            "curve-style": "haystack",
            opacity: 0.6,
          },
        },
      ],
      layout: { name: "fcose", quality: "default", animate: false, randomize: true, nodeSeparation: 75 } as cytoscape.LayoutOptions,
      wheelSensitivity: 0.2,
    });
    cy.on("tap", "node", (evt) => setSelected(evt.target.data("raw") as GraphNode));
    cy.on("tap", (evt) => {
      if (evt.target === cy) setSelected(null);
    });
    cyRef.current = cy;
    return () => {
      cy.destroy();
      cyRef.current = null;
    };
  }, [elements, net]);

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-2">
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
        <span className="text-xs text-[var(--muted)]">{MODES.find((m) => m.key === mode)?.hint}</span>
        {net && (
          <span className="ml-auto text-xs text-[var(--muted)]">
            {net.nodes.length} nodes · {net.edges.length} edges
            {net.stats?.truncated ? " · truncated" : ""}
          </span>
        )}
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[260px_1fr_300px]">
        {/* Left: node list */}
        <div className="card max-h-[70vh] overflow-y-auto">
          <div className="border-b p-2 text-xs font-semibold uppercase tracking-wide text-[var(--muted)]">
            Top nodes
          </div>
          {net &&
            [...net.nodes]
              .sort((a, b) => b.weight - a.weight)
              .slice(0, 100)
              .map((n) => (
                <button
                  key={n.id}
                  onClick={() => {
                    setSelected(n);
                    const ele = cyRef.current?.getElementById(n.id);
                    if (ele) {
                      cyRef.current?.elements().unselect();
                      ele.select();
                      cyRef.current?.animate({ center: { eles: ele }, zoom: 1.5 }, { duration: 300 });
                    }
                  }}
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

        {/* Middle: graph */}
        <div className="card relative h-[70vh] overflow-hidden">
          {loading && (
            <div className="absolute inset-0 grid place-items-center text-sm text-[var(--muted)]">
              Building network…
            </div>
          )}
          {error && (
            <div className="absolute inset-0 grid place-items-center p-6 text-center text-sm text-[#b91c1c]">
              {error}
            </div>
          )}
          {!loading && net && net.nodes.length === 0 && (
            <div className="absolute inset-0 grid place-items-center p-6 text-center text-sm text-[var(--muted)]">
              No network data for this mode. Citation needs extracted references; author/journal need
              collected metadata.
            </div>
          )}
          <div ref={containerRef} className="h-full w-full" />
        </div>

        {/* Right: details */}
        <div className="card max-h-[70vh] overflow-y-auto p-4">
          {selected ? (
            <div>
              <span className="badge" style={{ background: (TYPE_COLOR[selected.type] ?? "#94a3b8") + "22", color: TYPE_COLOR[selected.type] ?? "#475467" }}>
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
              Click a node to see details.
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
