"use client";

import Link from "next/link";
import { useActionState } from "react";

import type { FormState } from "@/lib/research-actions";
import { RESEARCH_STATUSES, TITLE_MAX_LENGTH } from "@/types/research";
import type { Research } from "@/types/research";

interface Props {
  action: (state: FormState, formData: FormData) => Promise<FormState>;
  research?: Research;
  submitLabel: string;
  cancelHref: string;
}

export function ResearchForm({ action, research, submitLabel, cancelHref }: Props) {
  const [state, formAction, pending] = useActionState(action, {} as FormState);
  const values = state.values ?? research;
  const fieldErrors = state.fieldErrors ?? {};

  return (
    <form action={formAction} className="card stack">
      {research ? <input type="hidden" name="id" value={research.id} /> : null}

      {state.error ? <p className="alert">{state.error}</p> : null}

      <label className="field">
        <span>
          Título <em>*</em>
        </span>
        <input
          name="title"
          defaultValue={values?.title ?? ""}
          maxLength={TITLE_MAX_LENGTH}
          required
          aria-invalid={Boolean(fieldErrors.title)}
        />
        {fieldErrors.title ? <small className="error">{fieldErrors.title}</small> : null}
      </label>

      <label className="field">
        <span>Objetivo</span>
        <textarea name="objective" rows={4} defaultValue={values?.objective ?? ""} required />
        {fieldErrors.objective ? <small className="error">{fieldErrors.objective}</small> : null}
      </label>

      <label className="field">
        <span>Pergunta de pesquisa</span>
        <textarea name="question" rows={3} defaultValue={values?.question ?? ""} required />
        {fieldErrors.question ? <small className="error">{fieldErrors.question}</small> : null}
      </label>

      <label className="field">
        <span>Status</span>
        <select name="status" defaultValue={values?.status ?? "DRAFT"}>
          {RESEARCH_STATUSES.map((status) => (
            <option key={status} value={status}>
              {status}
            </option>
          ))}
        </select>
        {fieldErrors.status ? <small className="error">{fieldErrors.status}</small> : null}
      </label>

      <div className="row">
        <button type="submit" className="btn primary" disabled={pending}>
          {pending ? "Salvando..." : submitLabel}
        </button>
        <Link href={cancelHref} className="btn">
          Cancelar
        </Link>
      </div>
    </form>
  );
}
