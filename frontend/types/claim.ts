export interface ResearchClaim {
  id: string;
  text: string;
  confidence?: number | null;
  validation_status?: string | null;
  document_id?: string | null;
  document_title?: string | null;
  evidence?: ClaimEvidence[];
}

export interface ClaimEvidence {
  id: string;
  text: string;
  document_id?: string | null;
  document_title?: string | null;
  page_number?: number | null;
}