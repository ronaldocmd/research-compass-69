export interface ResearchDocument {
  id: string;
  title: string;
  authors: string[];
  publication_year: number | null;
  doi: string | null;
  source: string;
  relevance_score: number | null;
  status: string;
}