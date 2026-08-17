import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  updateResearch: vi.fn(),
  deleteResearch: vi.fn(),
  revalidatePath: vi.fn(),
  redirect: vi.fn(() => {
    throw new Error("NEXT_REDIRECT");
  }),
}));

vi.mock("@/lib/api", () => ({
  ApiError: class ApiError extends Error {
    status: number;
    isNotFound: boolean;
    isValidation: boolean;
    fieldErrors: Record<string, string>;

    constructor(
      message: string,
      status: number,
      options: { fieldErrors?: Record<string, string> } = {},
    ) {
      super(message);
      this.status = status;
      this.isNotFound = status === 404;
      this.isValidation = status === 422;
      this.fieldErrors = options.fieldErrors ?? {};
    }
  },
  createResearch: vi.fn(),
  updateResearch: mocks.updateResearch,
  deleteResearch: mocks.deleteResearch,
}));

vi.mock("next/cache", () => ({
  revalidatePath: mocks.revalidatePath,
}));

vi.mock("next/navigation", () => ({
  redirect: mocks.redirect,
}));

import { ApiError } from "@/lib/api";
import {
  deleteResearchAction,
  updateResearchAction,
} from "@/lib/research-actions";

function formData(values: Record<string, string>) {
  const data = new FormData();
  for (const [key, value] of Object.entries(values)) data.set(key, value);
  return data;
}

const valid = {
  id: "research-123",
  title: "Título atualizado",
  objective: "Objetivo atualizado",
  question: "Pergunta atualizada",
  status: "DRAFT",
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe("RDA-009 updateResearchAction", () => {
  it("updates a valid research and redirects to its detail page", async () => {
    mocks.updateResearch.mockResolvedValue({ id: valid.id, ...valid });

    await expect(
      updateResearchAction(
        {},
        formData(valid),
      ),
    ).rejects.toThrow("NEXT_REDIRECT");

    expect(mocks.updateResearch).toHaveBeenCalledWith(valid.id, {
      title: valid.title,
      objective: valid.objective,
      question: valid.question,
      status: valid.status,
    });
    expect(mocks.revalidatePath).toHaveBeenCalledWith("/researches");
    expect(mocks.revalidatePath).toHaveBeenCalledWith(`/researches/${valid.id}`);
    expect(mocks.redirect).toHaveBeenCalledWith(`/researches/${valid.id}`);
  });

  it("rejects invalid edit data without calling the API", async () => {
    const data = formData({
      id: valid.id,
      title: "",
      objective: "",
      question: "",
      status: valid.status,
    });

    const result = await updateResearchAction({}, data);

    expect(mocks.updateResearch).not.toHaveBeenCalled();
    expect(result.fieldErrors).toEqual({
      title: "Título é obrigatório.",
      objective: "Objetivo é obrigatório.",
      question: "Pergunta é obrigatória.",
    });
    expect(result.values).toMatchObject({
      title: "",
      objective: "",
      question: "",
    });
  });

  it("returns a 404 error while preserving edited values", async () => {
    mocks.updateResearch.mockRejectedValue(new ApiError("not found", 404));

    const result = await updateResearchAction(
      {},
      formData(valid),
    );

    expect(result.error).toBe("Pesquisa não encontrada (404).");
    expect(result.values).toMatchObject({
      title: valid.title,
      objective: valid.objective,
      question: valid.question,
    });
    expect(mocks.redirect).not.toHaveBeenCalled();
  });

  it("returns an API error while preserving edited values", async () => {
    mocks.updateResearch.mockRejectedValue(
      new ApiError("Falha ao atualizar pesquisa", 500),
    );

    const result = await updateResearchAction({}, formData(valid));

    expect(result.error).toBe("Falha ao atualizar pesquisa");
    expect(result.values).toMatchObject({
      title: valid.title,
      objective: valid.objective,
      question: valid.question,
    });
    expect(mocks.redirect).not.toHaveBeenCalled();
  });
});

describe("RDA-009 deleteResearchAction", () => {
  it("deletes the research and redirects to the dashboard", async () => {
    mocks.deleteResearch.mockResolvedValue(undefined);

    await expect(
      deleteResearchAction(formData({ id: valid.id })),
    ).rejects.toThrow("NEXT_REDIRECT");

    expect(mocks.deleteResearch).toHaveBeenCalledWith(valid.id);
    expect(mocks.revalidatePath).toHaveBeenCalledWith("/researches");
    expect(mocks.redirect).toHaveBeenCalledWith("/researches");
  });

  it("does not redirect when deletion fails", async () => {
    mocks.deleteResearch.mockRejectedValue(
      new ApiError("Falha ao excluir pesquisa", 500),
    );

    await expect(
      deleteResearchAction(formData({ id: valid.id })),
    ).rejects.toThrow("Falha ao excluir pesquisa");

    expect(mocks.redirect).not.toHaveBeenCalled();
  });
});
