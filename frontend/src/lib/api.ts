import type {
  Article,
  ArticlePage,
  Network,
  NetworkMode,
  Project,
  ProjectSummary,
  Reference,
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
  category?: string;
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
  if (f.category && f.category !== "all") params.set("category", f.category);
  if (f.journal) params.set("journal", f.journal);
  if (f.view) params.set("view", f.view);
  if (f.sort) params.set("sort", f.sort);
  params.set("limit", String(f.limit ?? 100));
  params.set("offset", String(f.offset ?? 0));
  return get<ArticlePage>(`/api/projects/${projectId}/articles?${params.toString()}`);
}

async function post<T = { ok: boolean }>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { method: "POST" });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
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

export async function extractReferences(id: number): Promise<{ ok: boolean; count: number; references: Reference[] }> {
  const res = await fetch(`${BASE}/api/articles/${id}/extract`, { method: "POST" });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
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

export interface Completeness {
  total: number;
  complete: number;
  incomplete: number;
  fixable_with_doi: number;
  incomplete_no_doi: number;
  missing_by_field: Record<string, number>;
}
export interface EnrichStatus {
  job_id: string;
  total: number;
  completed: number;
  current: string;
  filled_fields: number;
  records_improved: number;
  log: string[];
  done: boolean;
  error: string | null;
}

export function getCompleteness(projectId: number): Promise<Completeness> {
  return get<Completeness>(`/api/projects/${projectId}/completeness`);
}
export function startEnrich(projectId: number): Promise<{ job_id: string; already_running: boolean }> {
  return post<{ job_id: string; already_running: boolean }>(`/api/projects/${projectId}/enrich`);
}
export function getEnrichStatus(jobId: string): Promise<EnrichStatus> {
  return get<EnrichStatus>(`/api/enrich/${jobId}`);
}
export function cancelEnrich(jobId: string) {
  return post(`/api/enrich/${jobId}/cancel`);
}
export function findActiveEnrich(projectId: number): Promise<{ job_id: string | null }> {
  return get<{ job_id: string | null }>(`/api/projects/${projectId}/enrich/active`);
}

export { BASE as API_BASE };
