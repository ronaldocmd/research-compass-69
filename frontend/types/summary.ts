import type { ResearchClaim } from "@/types/claim";
import type { ResearchDocument } from "@/types/document";
import type { ResearchEvidence } from "@/types/evidence";

export interface ResearchSummary {
  executive_summary?: string | null;
  claims?: ResearchClaim[];
  evidence?: ResearchEvidence[];
  limitations?: string[];
  gaps?: string[];
  sources?: ResearchDocument[];
}