"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { ApiError, createResearch, deleteResearch, updateResearch } from "@/lib/api";
import { RESEARCH_STATUSES, TITLE_MAX_LENGTH } from "@/types/research";
import type { ResearchCreateInput, ResearchStatus } from "@/types/research";

export interface FormState {
  error?: string;
  fieldErrors?: Record<string, string>;
  values?: {
    title: string;
    objective: string;
    question: string;
    status: ResearchStatus;
  };
}

function readForm(formData: FormData) {
  const rawStatus = String(formData.get("status") ?? "DRAFT");
  const status = (RESEARCH_STATUSES as string[]).includes(rawStatus)
    ? (rawStatus as ResearchStatus)
    : "DRAFT";
  return {
    title: String(formData.get("title") ?? "").trim(),
    objective: String(formData.get("objective") ?? "").trim(),
    question: String(formData.get("question") ?? "").trim(),
    status,
  };
}

/** Client-side mirror of the backend validation rules (title required, <=200). */
export function validate(values: ResearchCreateInput): Record<string, string> {
  const fieldErrors: Record<string, string> = {};
  if (!values.title) fieldErrors.title = "Título é obrigatório.";
  else if (values.title.length > TITLE_MAX_LENGTH)
    fieldErrors.title = `Título deve ter no máximo ${TITLE_MAX_LENGTH} caracteres.`;
  if (!values.objective) fieldErrors.objective = "Objetivo é obrigatório.";
  if (!values.question) fieldErrors.question = "Pergunta é obrigatória.";
  return fieldErrors;
}

export async function createResearchAction(
  _prev: FormState,
  formData: FormData,
): Promise<FormState> {
  const values = readForm(formData);
  const fieldErrors = validate(values);
  if (Object.keys(fieldErrors).length) return { fieldErrors, values };

  let id: string;
  try {
    const created = await createResearch(values);
    id = created.id;
  } catch (error) {
    return toFormState(error, values);
  }
  revalidatePath("/researches");
  redirect(`/researches/${id}`);
}

export async function updateResearchAction(
  _prev: FormState,
  formData: FormData,
): Promise<FormState> {
  const id = String(formData.get("id") ?? "");
  const values = readForm(formData);
  const fieldErrors = validate(values);
  if (Object.keys(fieldErrors).length) return { fieldErrors, values };

  try {
    await updateResearch(id, values);
  } catch (error) {
    return toFormState(error, values);
  }
  revalidatePath("/researches");
  revalidatePath(`/researches/${id}`);
  redirect(`/researches/${id}`);
}

export async function deleteResearchAction(formData: FormData): Promise<void> {
  const id = String(formData.get("id") ?? "");
  await deleteResearch(id);
  revalidatePath("/researches");
  redirect("/researches");
}

function toFormState(error: unknown, values: FormState["values"]): FormState {
  if (error instanceof ApiError) {
    if (error.isValidation) return { error: error.message, fieldErrors: error.fieldErrors, values };
    if (error.isNotFound) return { error: "Pesquisa não encontrada (404).", values };
    return { error: error.message, values };
  }
  return { error: "Erro inesperado.", values };
}
