import { TITLE_MAX_LENGTH } from "@/types/research";
import type { ResearchCreateInput } from "@/types/research";

/** Mirrors the backend validation rules (title required, max 200 chars). */
export function validate(values: ResearchCreateInput): Record<string, string> {
  const fieldErrors: Record<string, string> = {};
  if (!values.title) fieldErrors.title = "Título é obrigatório.";
  else if (values.title.length > TITLE_MAX_LENGTH)
    fieldErrors.title = `Título deve ter no máximo ${TITLE_MAX_LENGTH} caracteres.`;
  if (!values.objective) fieldErrors.objective = "Objetivo é obrigatório.";
  if (!values.question) fieldErrors.question = "Pergunta é obrigatória.";
  return fieldErrors;
}
