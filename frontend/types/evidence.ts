export interface ResearchEvidence {
  id: string;
  text: string | null;
  status: string;
  document_id?: string | null;
  document_title?: string | null;
  document_source?: string | null;
  claim_id?: string | null;
  claim_text?: string | null;
  chunk_id?: string | null;
  page_number?: number | null;
  section?: string | null;
}