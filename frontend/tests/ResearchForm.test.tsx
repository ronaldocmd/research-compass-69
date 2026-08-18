import React from "react";
import { describe, expect, it, vi, afterEach } from "vitest";
import { render, screen, fireEvent, act, cleanup } from "@testing-library/react";

import { ResearchForm } from "@/components/ResearchForm";
import type { FormState } from "@/lib/research-actions";
import type { Research } from "@/types/research";

const baseResearch: Research = {
  id: "research-123",
  title: "Título existente",
  objective: "Objetivo existente",
  question: "Pergunta existente",
  status: "DRAFT",
  created_at: "2026-08-15T10:00:00Z",
  updated_at: "2026-08-15T10:00:00Z",
};

describe("RDA-010 ResearchForm", () => {
  afterEach(() => {
    cleanup();
  });

  it("renders create form with empty fields when no research is provided", () => {
    render(
      <ResearchForm
        action={async () => ({})}
        submitLabel="Criar"
        cancelHref="/researches"
      />,
    );

    expect(screen.getByLabelText(/Título/)).toHaveValue("");
    expect(screen.getByLabelText(/Objetivo/)).toHaveValue("");
    expect(screen.getByLabelText(/Pergunta de pesquisa/)).toHaveValue("");
    expect(screen.getByLabelText(/Status/)).toHaveValue("DRAFT");
    expect(screen.getByRole("button", { name: "Criar" })).toBeInTheDocument();
  });

  it("renders edit form with existing research values", () => {
    render(
      <ResearchForm
        action={async () => ({})}
        research={baseResearch}
        submitLabel="Salvar"
        cancelHref={`/researches/${baseResearch.id}`}
      />,
    );

    expect(screen.getByLabelText(/Título/)).toHaveValue(baseResearch.title);
    expect(screen.getByLabelText(/Objetivo/)).toHaveValue(baseResearch.objective);
    expect(screen.getByLabelText(/Pergunta de pesquisa/)).toHaveValue(baseResearch.question);
    expect(screen.getByLabelText(/Status/)).toHaveValue(baseResearch.status);
    expect(screen.getByRole("button", { name: "Salvar" })).toBeInTheDocument();
  });

  it("shows field errors when action returns them", async () => {
    const errorState: FormState = {
      fieldErrors: {
        title: "Título é obrigatório.",
        objective: "Objetivo é obrigatório.",
        question: "Pergunta é obrigatória.",
      },
      values: { title: "", objective: "", question: "", status: "DRAFT" },
    };

    const actionWithError = vi.fn(async () => errorState);

    render(
      <ResearchForm
        action={actionWithError}
        submitLabel="Criar"
        cancelHref="/researches"
      />,
    );

    const form = screen.getByRole("button", { name: "Criar" }).closest("form")!;
    await act(async () => {
      form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    });

    expect(screen.getByText("Título é obrigatório.")).toBeInTheDocument();
    expect(screen.getByText("Objetivo é obrigatório.")).toBeInTheDocument();
    expect(screen.getByText("Pergunta é obrigatória.")).toBeInTheDocument();
  });

  it("shows a general error when action returns it", async () => {
    const errorState: FormState = {
      error: "Erro inesperado.",
    };

    const actionWithError = vi.fn(async () => errorState);

    render(
      <ResearchForm
        action={actionWithError}
        submitLabel="Criar"
        cancelHref="/researches"
      />,
    );

    const form = screen.getByRole("button", { name: "Criar" }).closest("form")!;
    await act(async () => {
      form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    });

    expect(screen.getByText("Erro inesperado.")).toBeInTheDocument();
  });

  it("disables submit button while pending", async () => {
    let resolve: (value: FormState) => void;
    const pendingAction = async () =>
      new Promise<FormState>((r) => {
        resolve = r;
      });

    render(
      <ResearchForm
        action={pendingAction}
        submitLabel="Salvando..."
        cancelHref="/researches"
      />,
    );

    const form = screen.getByRole("button", { name: "Salvando..." }).closest("form")!;
    await act(async () => {
      form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    });

    const button = screen.getByRole("button", { name: "Salvando..." });
    expect(button).toBeDisabled();
    resolve!({});
  });
});
