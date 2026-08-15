export type ResearchStatus = "DRAFT" | "READY";

export const RESEARCH_STATUSES: ResearchStatus[] = ["DRAFT", "READY"];

export const TITLE_MAX_LENGTH = 200;

/** Mirrors backend ResearchResponse (app/schemas/research.py). */
export interface Research {
  id: string;
  title: string;
  objective: string;
  question: string;
  status: ResearchStatus;
  created_at: string;
  updated_at: string;
}

/** Mirrors backend ResearchCreate. */
export interface ResearchCreateInput {
  title: string;
  objective: string;
  question: string;
  status?: ResearchStatus;
}

/** Mirrors backend ResearchUpdate (all fields optional). */
export type ResearchUpdateInput = Partial<ResearchCreateInput>;
