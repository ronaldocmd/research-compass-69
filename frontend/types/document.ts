export interface ResearchDocument {
  id: string;
  title: string;
  authors: string[];
  publication_year: number | null;
  doi: string | null;
  source: string;
  relevance_score: number | null;
  status: string;
  url?: string | null;
  abstract?: string | null;
  chunks?: DocumentChunk[];
  claims?: DocumentClaim[];
  evidence?: DocumentEvidence[];
}

export interface DocumentChunk {
  id: string;
  text: string;
  page_number?: number | null;
  section?: string | null;
}

export interface DocumentClaim {
  id: string;
  text: string;
  confidence?: number | null;
  page_number?: number | null;
}

export interface DocumentEvidence {
  id: string;
  text: string;
  page_number?: number | null;
  section?: string | null;
}