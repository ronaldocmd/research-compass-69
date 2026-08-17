import {
  OBJECTIVE_MAX_LENGTH,
  QUESTION_MAX_LENGTH,
  TITLE_MAX_LENGTH,
} from "@/types/research";
import type { ResearchCreateInput } from "@/types/research";

/** Mirrors the backend validation rules for ResearchCreate/ResearchUpdate. */
export function validate(values: ResearchCreateInput): Record<string, string> {
  const fieldErrors: Record<string, string> = {};
  if (!values.title) fieldErrors.title = "Título é obrigatório.";
  else if (values.title.length > TITLE_MAX_LENGTH)
    fieldErrors.title = `Título deve ter no máximo ${TITLE_MAX_LENGTH} caracteres.`;
  if (!values.objective) fieldErrors.objective = "Objetivo é obrigatório.";
  else if (values.objective.length > OBJECTIVE_MAX_LENGTH)
    fieldErrors.objective = `Objetivo deve ter no máximo ${OBJECTIVE_MAX_LENGTH} caracteres.`;
  if (!values.question) fieldErrors.question = "Pergunta é obrigatória.";
  else if (values.question.length > QUESTION_MAX_LENGTH)
    fieldErrors.question = `Pergunta deve ter no máximo ${QUESTION_MAX_LENGTH} caracteres.`;
  return fieldErrors;
}
