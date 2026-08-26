export type PlanTaskStatus = "PENDING" | "IN_PROGRESS" | "COMPLETED" | "FAILED" | "SKIPPED";

export interface PlanTask {
  id: string;
  title: string;
  description: string;
  priority: number;
  task_type: string;
  status: PlanTaskStatus;
  order: number;
  result_summary: string | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export interface ResearchPlan {
  id: string;
  research_id: string;
  status: string;
  created_at: string;
  updated_at: string;
  tasks: PlanTask[];
}