import type {
  Article,
  ArticlePage,
  Network,
  NetworkMode,
  Project,
  ProjectSummary,
} from "./types";

const BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText} for ${path}`);
  return res.json() as Promise<T>;
}

export async function listProjects(): Promise<ProjectSummary[]> {
  return get<ProjectSummary[]>("/api/projects");
}

export async function getProject(id: number): Promise<Project> {
  return get<Project>(`/api/projects/${id}`);
}

export interface ArticleFilters {
  q?: string;
  decision?: string;
  year_min?: number;
  pub_type?: string;
  journal?: string;
  view?: "active" | "trash";
  sort?: "year" | "citations";
  limit?: number;
  offset?: number;
}

export async function listArticles(projectId: number, f: ArticleFilters = {}): Promise<ArticlePage> {
  const params = new URLSearchParams();
  if (f.q) params.set("q", f.q);
  if (f.decision && f.decision !== "all") params.set("decision", f.decision);
  if (f.year_min) params.set("year_min", String(f.year_min));
  if (f.pub_type && f.pub_type !== "all") params.set("pub_type", f.pub_type);
  if (f.journal) params.set("journal", f.journal);
  if (f.view) params.set("view", f.view);
  if (f.sort) params.set("sort", f.sort);
  params.set("limit", String(f.limit ?? 100));
  params.set("offset", String(f.offset ?? 0));
  return get<ArticlePage>(`/api/projects/${projectId}/articles?${params.toString()}`);
}

async function post(path: string): Promise<{ ok: boolean }> {
  const res = await fetch(`${BASE}${path}`, { method: "POST" });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

export function trashArticle(id: number) {
  return post(`/api/articles/${id}/trash`);
}
export function restoreArticle(id: number) {
  return post(`/api/articles/${id}/restore`);
}
export async function deleteArticlePermanently(id: number) {
  const res = await fetch(`${BASE}/api/articles/${id}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}
export function emptyTrash(projectId: number) {
  return post(`/api/projects/${projectId}/trash/empty`);
}

export async function getArticle(id: number, withReferences = false): Promise<Article> {
  return get<Article>(`/api/articles/${id}?with_references=${withReferences}`);
}

export async function editArticle(id: number, patch: Partial<Article>): Promise<{ ok: boolean; changed: string[]; article: Article }> {
  const res = await fetch(`${BASE}/api/articles/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

export async function getNetwork(projectId: number, mode: NetworkMode): Promise<Network> {
  return get<Network>(`/api/projects/${projectId}/network?mode=${mode}`);
}

export { BASE as API_BASE };
