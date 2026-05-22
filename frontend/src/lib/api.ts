import type {
  Article,
  ArticlePage,
  Network,
  NetworkFilters,
  NetworkMode,
  Project,
  ProjectSummary,
  Reference,
  ReferencePanel,
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

export interface NewProject {
  name: string;
  topic: string;
  type: string; // review | research | both
  description?: string;
}

export async function createProject(
  body: NewProject,
): Promise<{ id: number; name: string; topic: string; literature_type: string }> {
  const res = await fetch(`${BASE}/api/projects`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

export async function deleteProject(id: number): Promise<{ ok: boolean; deleted: Record<string, number> }> {
  const res = await fetch(`${BASE}/api/projects/${id}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

export async function renameProject(
  id: number,
  patch: { name?: string; topic?: string; description?: string },
): Promise<{ id: number; name: string; topic: string }> {
  const res = await fetch(`${BASE}/api/projects/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

export async function duplicateProject(id: number): Promise<{ id: number; name: string }> {
  const res = await fetch(`${BASE}/api/projects/${id}/duplicate`, { method: "POST" });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

export async function suggestKeywords(
  topic: string,
  seeds: string[],
): Promise<{ terms: string[]; unavailable: boolean }> {
  return postJson(`/api/keyword-suggest`, { topic, seeds });
}

export interface ArticleFilters {
  q?: string;
  decision?: string;
  year_min?: number;
  year_max?: number;
  pub_type?: string;
  category?: string;
  journal?: string;
  origin?: "all" | "search" | "reference";
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
  if (f.year_max) params.set("year_max", String(f.year_max));
  if (f.pub_type && f.pub_type !== "all") params.set("pub_type", f.pub_type);
  if (f.category && f.category !== "all") params.set("category", f.category);
  if (f.journal) params.set("journal", f.journal);
  if (f.origin && f.origin !== "all") params.set("origin", f.origin);
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

export async function getNetwork(projectId: number, mode: NetworkMode, filters: NetworkFilters = {}): Promise<Network> {
  const p = new URLSearchParams({ mode });
  if (filters.year_min) p.set("year_min", String(filters.year_min));
  if (filters.year_max) p.set("year_max", String(filters.year_max));
  if (filters.included_only) p.set("included_only", "true");
  if (filters.min_citations) p.set("min_citations", String(filters.min_citations));
  return get<Network>(`/api/projects/${projectId}/network?${p.toString()}`);
}

// References companion panel.
export function getArticleReferences(id: number): Promise<ReferencePanel> {
  return get<ReferencePanel>(`/api/articles/${id}/references`);
}
export function collectReference(id: number, doi: string): Promise<{ added: number; linked: number; error?: string }> {
  return postJson(`/api/articles/${id}/references/collect`, { doi });
}
export function collectAllReferences(
  id: number,
): Promise<{ added: number; linked: number; resolved: number; requested: number }> {
  return postJson(`/api/articles/${id}/references/collect-all`, {});
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

export interface IncompleteArticle {
  id: number;
  title: string;
  year: number | null;
  venue: string;
  doi: string;
  has_doi: boolean;
  missing: string[];
}

export function getCompleteness(projectId: number): Promise<Completeness> {
  return get<Completeness>(`/api/projects/${projectId}/completeness`);
}
export function listIncomplete(projectId: number, limit = 500): Promise<{ items: IncompleteArticle[] }> {
  return get<{ items: IncompleteArticle[] }>(`/api/projects/${projectId}/incomplete?limit=${limit}`);
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

// Search / collect

export interface SearchStatus {
  job_id: string;
  project_id: number;
  mode: string;
  total: number;
  completed: number;
  current_query: string;
  log: string[];
  total_added: number;
  total_skipped: number;
  duplicates_removed: number;
  done: boolean;
  error: string | null;
}

export interface SearchParams {
  queries: string[];
  type: string; // review | research | both
  year_from?: number | null;
  year_to?: number | null;
  sources: string[]; // openalex | pubmed | s2 | arxiv
  max_per_source: number;
  title_keyword: string;
  match_mode: string; // any | all
}

export async function startSearch(
  projectId: number,
  params: SearchParams,
): Promise<{ job_id: string; already_running: boolean }> {
  const res = await fetch(`${BASE}/api/projects/${projectId}/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

export function getSearchStatus(jobId: string): Promise<SearchStatus> {
  return get<SearchStatus>(`/api/search/${jobId}`);
}
export function cancelSearch(jobId: string) {
  return post(`/api/search/${jobId}/cancel`);
}
export function findActiveSearch(projectId: number, type: string): Promise<{ job_id: string | null }> {
  return get<{ job_id: string | null }>(`/api/projects/${projectId}/search/active?type=${type}`);
}

export async function bulkDecision(projectId: number, ids: number[], status: string) {
  const res = await fetch(`${BASE}/api/projects/${projectId}/bulk-decision`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ids, status }),
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}
export async function bulkTrash(projectId: number, ids: number[]) {
  const res = await fetch(`${BASE}/api/projects/${projectId}/bulk-trash`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ids }),
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

export interface ScreeningStats {
  total: number;
  unscreened: number;
  include: number;
  maybe: number;
  exclude: number;
  from_search: number;
  from_reference: number;
  refs_extracted: number;
}

// Reference harvest + analysis (snowballing / gap detection)

export interface HarvestStatus {
  job_id: string;
  project_id: number;
  requested: number;
  skipped_no_doi: number;
  skipped_done: number;
  total: number;
  completed: number;
  with_refs: number;
  total_refs: number;
  current: string;
  log: string[];
  done: boolean;
  error: string | null;
}

export interface MissingRef {
  key: string;
  title: string;
  doi: string;
  year: number | null;
  venue: string;
  authors: string;
  cited_by: number;
}

export interface AnalysisResult {
  papers_analyzed: number;
  unique_references: number;
  in_library: number;
  copied_from_other_projects: number;
  missing_total?: number;
  missing_count: number;
  missing: MissingRef[];
  other_project_names?: string[];
}

export function startHarvest(projectId: number, articleIds: number[] = []): Promise<{ job_id: string; already_running: boolean }> {
  return postJson(`/api/projects/${projectId}/harvest-refs`, { article_ids: articleIds, scope: articleIds.length ? "selected" : "all" });
}
export function getHarvestStatus(jobId: string): Promise<HarvestStatus> {
  return get<HarvestStatus>(`/api/refs/${jobId}`);
}
export function cancelHarvest(jobId: string) {
  return post(`/api/refs/${jobId}/cancel`);
}
export function findActiveHarvest(projectId: number): Promise<{ job_id: string | null }> {
  return get<{ job_id: string | null }>(`/api/projects/${projectId}/refs/active`);
}
export interface CaptureStatus {
  job_id: string;
  project_id: number;
  phase: string;
  total: number;
  completed: number;
  no_doi: number;
  done: boolean;
  error: string | null;
  result: AnalysisResult | null;
}
export function startCapture(projectId: number): Promise<{ job_id: string; already_running: boolean }> {
  return postJson(`/api/projects/${projectId}/capture-refs`, { article_ids: [], scope: "all" });
}
export function getCaptureStatus(jobId: string): Promise<CaptureStatus> {
  return get<CaptureStatus>(`/api/capture/${jobId}`);
}
export function findActiveCapture(
  projectId: number,
): Promise<{ job_id: string | null; latest_result: AnalysisResult | null }> {
  return get<{ job_id: string | null; latest_result: AnalysisResult | null }>(
    `/api/projects/${projectId}/capture/active`,
  );
}

export function buildAnalysis(projectId: number): Promise<AnalysisResult> {
  return postJson(`/api/projects/${projectId}/analysis/build`, {});
}
export function collectRefs(projectId: number, items: MissingRef[]): Promise<{ added: number }> {
  return postJson(`/api/projects/${projectId}/collect-refs`, { items });
}

export interface YearPoint {
  year: number;
  count: number;
  cumulative: number;
}
export interface NameCount {
  name: string;
  count: number;
}
export interface FoundationalPaper {
  id: number;
  title: string;
  year: number | null;
  venue: string;
  internal_cited_by: number;
  citation_count: number | null;
}
export interface Insights {
  total: number;
  from_search: number;
  from_reference: number;
  papers_with_refs: number;
  year_min: number | null;
  year_max: number | null;
  by_year: YearPoint[];
  top_authors: NameCount[];
  top_venues: NameCount[];
  foundational: FoundationalPaper[];
  screening: Record<string, number>;
}
export function getInsights(projectId: number): Promise<Insights> {
  return get<Insights>(`/api/projects/${projectId}/insights`);
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}
export function getScreeningStats(projectId: number): Promise<ScreeningStats> {
  return get<ScreeningStats>(`/api/projects/${projectId}/screening-stats`);
}

// Full-metadata export download URL (CSV / JSON / Excel).
export function exportUrl(projectId: number, format: "csv" | "json" | "xlsx"): string {
  return `${BASE}/api/projects/${projectId}/export?format=${format}`;
}

export { BASE as API_BASE };
