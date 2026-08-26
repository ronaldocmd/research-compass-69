export interface WorkflowBudget {
  llm_calls?: number;
  search_calls?: number;
  processing_operations?: number;
  total_tokens?: number;
  estimated_cost_usd?: number;
  max_cost_usd?: number;
  is_exceeded?: boolean;
}

/** Partial shape of the existing workflow status response. */
export interface WorkflowStatus {
  current_stage?: string;
  stage?: string;
  search_results?: unknown[];
  selected_documents?: unknown[];
  processed_document_ids?: unknown[];
  claims?: unknown[];
  evidence_items?: unknown[];
  errors?: unknown[];
  budget?: WorkflowBudget;
}