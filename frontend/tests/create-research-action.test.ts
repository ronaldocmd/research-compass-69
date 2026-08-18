import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  createResearch: vi.fn(),
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
  createResearch: mocks.createResearch,
}));

vi.mock("next/cache", () => ({
  revalidatePath: mocks.revalidatePath,
}));

vi.mock("next/navigation", () => ({
  redirect: mocks.redirect,
}));

import { ApiError } from "@/lib/api";
import { createResearchAction } from "@/lib/research-actions";

function formData(values: Record<string, string>) {
  const data = new FormData();
  for (const [key, value] of Object.entries(values)) data.set(key, value);
  return data;
}

const valid = {
  title: "Novo título",
  objective: "Objetivo",
  question: "Pergunta",
  status: "DRAFT",
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe("RDA-010 createResearchAction", () => {
  it("creates a valid research and redirects to its detail page", async () => {
    const created = { id: "research-123", ...valid };
    mocks.createResearch.mockResolvedValue(created);

    await expect(
      createResearchAction({}, formData(valid)),
    ).rejects.toThrow("NEXT_REDIRECT");

    expect(mocks.createResearch).toHaveBeenCalledWith({
      title: valid.title,
      objective: valid.objective,
      question: valid.question,
      status: valid.status,
    });
    expect(mocks.revalidatePath).toHaveBeenCalledWith("/researches");
    expect(mocks.redirect).toHaveBeenCalledWith("/researches/research-123");
  });

  it("rejects invalid create data without calling the API", async () => {
    const data = formData({
      title: "",
      objective: "",
      question: "",
      status: valid.status,
    });

    const result = await createResearchAction({}, data);

    expect(mocks.createResearch).not.toHaveBeenCalled();
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

  it("returns a 422 API error while preserving values", async () => {
    mocks.createResearch.mockRejectedValue(
      new ApiError("Dados inválidos", 422, {
        fieldErrors: { title: "String should have at most 200 characters" },
      }),
    );

    const result = await createResearchAction({}, formData(valid));

    expect(result.error).toBe("Dados inválidos");
    expect(result.fieldErrors?.title).toContain("200");
    expect(result.values).toMatchObject(valid);
    expect(mocks.redirect).not.toHaveBeenCalled();
  });

  it("returns a generic API error while preserving values", async () => {
    mocks.createResearch.mockRejectedValue(
      new ApiError("Falha ao criar pesquisa", 500),
    );

    const result = await createResearchAction({}, formData(valid));

    expect(result.error).toBe("Falha ao criar pesquisa");
    expect(result.values).toMatchObject(valid);
    expect(mocks.redirect).not.toHaveBeenCalled();
  });
});
