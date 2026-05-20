"use client";

import { useCallback, useEffect, useState } from "react";
import { deleteArticlePermanently, emptyTrash, listArticles, restoreArticle } from "@/lib/api";
import type { Article } from "@/lib/types";

export default function Trash({ projectId }: { projectId: number }) {
  const [items, setItems] = useState<Article[]>([]);
  const [loading, setLoading] = useState(true);
  const [confirmEmpty, setConfirmEmpty] = useState(false);

  const reload = useCallback(() => {
    setLoading(true);
    return listArticles(projectId, { view: "trash", limit: 500 })
      .then((r) => setItems(r.items))
      .finally(() => setLoading(false));
  }, [projectId]);

  useEffect(() => {
    reload();
  }, [reload]);

  const restore = async (id: number) => {
    await restoreArticle(id);
    setItems((prev) => prev.filter((a) => a.id !== id));
  };
  const wipe = async (id: number) => {
    await deleteArticlePermanently(id);
    setItems((prev) => prev.filter((a) => a.id !== id));
  };

  return (
    <div>
      <div className="mb-3 flex items-center justify-between">
        <p className="text-sm text-[var(--muted)]">
          Deleted papers live here. <b>Restore</b> puts them back in the library; <b>Delete forever</b> removes
          them permanently. (This is separate from the “exclude” screening decision.)
        </p>
        {items.length > 0 &&
          (confirmEmpty ? (
            <span className="flex items-center gap-2 text-sm">
              <span className="text-[#b91c1c]">Permanently delete all {items.length}?</span>
              <button
                className="btn"
                style={{ color: "#b91c1c", borderColor: "#fecaca" }}
                onClick={async () => {
                  await emptyTrash(projectId);
                  setConfirmEmpty(false);
                  reload();
                }}
              >
                Yes, empty trash
              </button>
              <button className="btn" onClick={() => setConfirmEmpty(false)}>
                Cancel
              </button>
            </span>
          ) : (
            <button className="btn" onClick={() => setConfirmEmpty(true)}>
              Empty trash
            </button>
          ))}
      </div>

      <div className="card overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b bg-[var(--surface-2)] text-left text-xs uppercase tracking-wide text-[var(--muted)]">
              <th className="px-3 py-2 font-medium">Title</th>
              <th className="px-3 py-2 font-medium">Journal</th>
              <th className="px-3 py-2 font-medium">Year</th>
              <th className="px-3 py-2 font-medium">Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr>
                <td colSpan={4} className="px-3 py-6 text-center text-[var(--muted)]">
                  Loading…
                </td>
              </tr>
            )}
            {!loading &&
              items.map((a) => (
                <tr key={a.id} className="border-b last:border-0 hover:bg-[var(--surface-2)]">
                  <td className="px-3 py-2">
                    <div className="line-clamp-2">{a.title}</div>
                    <div className="text-xs text-[var(--muted)]">{a.authors}</div>
                  </td>
                  <td className="px-3 py-2 text-xs italic text-[var(--muted)]">{a.venue || "—"}</td>
                  <td className="px-3 py-2 tabular-nums">{a.year ?? ""}</td>
                  <td className="px-3 py-2">
                    <div className="flex gap-2">
                      <button className="btn" onClick={() => restore(a.id)}>
                        Restore
                      </button>
                      <button
                        className="btn"
                        style={{ color: "#b91c1c", borderColor: "#fecaca" }}
                        onClick={() => wipe(a.id)}
                      >
                        Delete forever
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            {!loading && items.length === 0 && (
              <tr>
                <td colSpan={4} className="px-3 py-10 text-center text-sm text-[var(--muted)]">
                  Trash is empty.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
