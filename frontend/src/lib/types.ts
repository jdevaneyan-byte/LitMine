export interface ProjectSummary {
  id: number;
  name: string;
  topic: string;
  literature_type: string;
  description: string;
  library: number;
  curated_reviews: number;
  cited: number;
}

export interface Project {
  id: number;
  name: string;
  topic: string;
  literature_type: string;
  description: string;
}

export interface Article {
  id: number;
  title: string;
  authors: string;
  year: number | null;
  doi: string | null;
  url: string | null;
  abstract: string | null;
  source: string;
  pub_type: string | null;
  category: string;
  field?: string;
  field_source?: string;
  venue: string;
  citation_count: number | null;
  screening_status: string;
  tags: string;
  notes: string;
  decision_reason: string;
  is_deleted: boolean;
  abstract_unavailable?: boolean;
  origin?: string; // "search" | "reference"
  references_extracted: boolean;
  references_count: number;
  references_with_doi?: number; // references that carry a DOI (collectable)
  references_in_library?: number; // of those, how many are already collected
  edited_by_user: boolean;
  references?: Reference[];
  references_error?: string;
}

export interface AnnotatedReference {
  title: string;
  doi: string;
  year: number | null;
  authors: string;
  venue: string;
  status: "in_library" | "collectable" | "no_doi";
  library_id: number | null;
  linked: boolean;
}

export interface ReferencePanel {
  article_id: number;
  total: number;
  in_library: number;
  collectable: number;
  no_doi: number;
  added: number;
  references: AnnotatedReference[];
}

export interface Reference {
  title: string;
  doi: string;
  year: number | null;
  authors: string;
  venue: string;
  is_review: boolean;
  is_book: boolean;
  source: string;
  url: string;
}

export interface ArticlePage {
  total: number;
  items: Article[];
}

export interface GraphNode {
  id: string;
  label: string;
  type: string;
  weight: number;
  year?: number | null;
  doi?: string;
  cited_by_count?: number;
  papers?: number;
  article_id?: number; // citation-mode nodes link back to a Library row
}

export interface NetworkFilters {
  year_min?: number;
  year_max?: number;
  included_only?: boolean;
  min_citations?: number;
}

export interface GraphEdge {
  source: string;
  target: string;
  type: string;
  weight?: number;
}

export interface Network {
  mode: string;
  nodes: GraphNode[];
  edges: GraphEdge[];
  stats: Record<string, number | boolean>;
}

export type NetworkMode = "citation" | "author" | "journal";
