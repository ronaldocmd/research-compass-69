export type ResearchEventType = "planning" | "search" | "document" | "processing" | "evidence" | "synthesis" | "error" | "budget";

export interface ResearchEvent {
  id: string;
  event_type: ResearchEventType;
  message: string;
  timestamp: string;
  severity?: string | null;
}