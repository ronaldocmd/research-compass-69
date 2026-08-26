import type { HealthResponse } from "@/types/health";
import type { Research, ResearchCreateInput, ResearchUpdateInput } from "@/types/research";
import type { WorkflowStatus } from "@/types/workflow";

/**
 * Base URL of the Research API.
 * - Server side (containers / SSR): API_INTERNAL_URL (e.g. http://backend:8000)
 * - Browser: NEXT_PUBLIC_API_URL (e.g. http://localhost:8000)
 */
export function getApiBaseUrl(): string {
  const serverUrl = typeof window === "undefined" ? process.env.API_INTERNAL_URL : undefined;
  return serverUrl ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
}

export class ApiError extends Error {
  readonly status: number;
  /** Field-level messages parsed from FastAPI 422 responses. */
  readonly fieldErrors: Record<string, string>;

  constructor(status: number, message: string, fieldErrors: Record<string, string> = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.fieldErrors = fieldErrors;
  }

  get isNotFound(): boolean {
    return this.status === 404;
  }

  get isValidation(): boolean {
    return this.status === 422;
  }
}

type FastApiDetailItem = { loc?: unknown[]; msg?: string };

export function parseValidationDetail(detail: unknown): Record<string, string> {
  if (!Array.isArray(detail)) return {};
  const errors: Record<string, string> = {};
  for (const item of detail as FastApiDetailItem[]) {
    const loc = Array.isArray(item?.loc) ? item.loc : [];
    const field = loc.length ? String(loc[loc.length - 1]) : "_";
    if (!errors[field] && item?.msg) errors[field] = item.msg;
  }
  return errors;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${getApiBaseUrl()}${path}`, {
      ...init,
      cache: "no-store",
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch {
    throw new ApiError(0, "Não foi possível contactar a Research API.");
  }

  if (response.status === 204) return undefined as T;

  const raw = await response.text();
  const body: unknown = raw ? safeJson(raw) : null;

  if (!response.ok) {
    const detail = (body as { detail?: unknown } | null)?.detail;
    if (response.status === 422) {
      throw new ApiError(422, "Dados inválidos.", parseValidationDetail(detail));
    }
    const message = typeof detail === "string" ? detail : `Erro ${response.status} na Research API.`;
    throw new ApiError(response.status, message);
  }

  return body as T;
}

function safeJson(raw: string): unknown {
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

export async function getBackendHealth(): Promise<HealthResponse | null> {
  try {
    return await request<HealthResponse>("/api/v1/health");
  } catch {
    return null;
  }
}

export function listResearches(params: { limit?: number; offset?: number } = {}) {
  const search = new URLSearchParams();
  if (params.limit != null) search.set("limit", String(params.limit));
  if (params.offset != null) search.set("offset", String(params.offset));
  const qs = search.toString();
  return request<Research[]>(`/api/v1/researches${qs ? `?${qs}` : ""}`);
}

export function getResearch(id: string) {
  return request<Research>(`/api/v1/researches/${id}`);
}

export function createResearch(payload: ResearchCreateInput) {
  return request<Research>("/api/v1/researches", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateResearch(id: string, payload: ResearchUpdateInput) {
  return request<Research>(`/api/v1/researches/${id}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function deleteResearch(id: string) {
  return request<void>(`/api/v1/researches/${id}`, { method: "DELETE" });
}

export function getWorkflowStatus(id: string) {
  return request<WorkflowStatus>(`/api/v1/researches/${id}/status`);
}
