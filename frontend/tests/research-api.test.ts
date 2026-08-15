import { afterEach, describe, expect, it, vi } from "vitest";

import {
  ApiError,
  createResearch,
  deleteResearch,
  getApiBaseUrl,
  getResearch,
  listResearches,
  parseValidationDetail,
  updateResearch,
} from "../lib/api";
import { validate } from "../lib/research-validation";
import type { Research } from "../types/research";

const sample: Research = {
  id: "6f0f9d68-4e1b-4a5f-9a2c-6a4b7a1d6d11",
  title: "Impacto de LLMs na revisão de literatura",
  objective: "Mapear o estado da arte",
  question: "Como LLMs auxiliam revisões sistemáticas?",
  status: "DRAFT",
  created_at: "2026-08-15T10:00:00Z",
  updated_at: "2026-08-15T10:00:00Z",
};

function mockFetch(status: number, body: unknown) {
  const spy = vi.fn(async () =>
    new Response(status === 204 ? null : JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  );
  vi.stubGlobal("fetch", spy);
  return spy;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("api base url", () => {
  it("falls back to localhost:8000", () => {
    expect(getApiBaseUrl()).toBe(process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000");
  });
});

describe("research client", () => {
  it("lists researches with pagination params", async () => {
    const spy = mockFetch(200, [sample]);
    const result = await listResearches({ limit: 10, offset: 5 });
    expect(result).toHaveLength(1);
    expect(String(spy.mock.calls[0][0])).toContain("/api/v1/researches?limit=10&offset=5");
  });

  it("creates a research via POST", async () => {
    const spy = mockFetch(201, sample);
    const created = await createResearch({
      title: sample.title,
      objective: sample.objective,
      question: sample.question,
      status: "DRAFT",
    });
    expect(created.id).toBe(sample.id);
    expect(spy.mock.calls[0][1]).toMatchObject({ method: "POST" });
  });

  it("updates a research via PATCH", async () => {
    const spy = mockFetch(200, { ...sample, status: "READY" });
    const updated = await updateResearch(sample.id, { status: "READY" });
    expect(updated.status).toBe("READY");
    expect(spy.mock.calls[0][1]).toMatchObject({ method: "PATCH" });
  });

  it("deletes a research and tolerates 204 without body", async () => {
    mockFetch(204, null);
    await expect(deleteResearch(sample.id)).resolves.toBeUndefined();
  });

  it("maps 404 to an ApiError flagged as not found", async () => {
    mockFetch(404, { detail: "Research not found" });
    await expect(getResearch(sample.id)).rejects.toMatchObject({
      status: 404,
      isNotFound: true,
    });
  });

  it("maps 422 to field errors", async () => {
    mockFetch(422, {
      detail: [{ loc: ["body", "title"], msg: "String should have at most 200 characters" }],
    });
    const error = await createResearch({ title: "x", objective: "y", question: "z" }).catch(
      (err) => err,
    );
    expect(error).toBeInstanceOf(ApiError);
    expect(error.isValidation).toBe(true);
    expect(error.fieldErrors.title).toContain("200");
  });

  it("wraps network failures", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new Error("ECONNREFUSED");
      }),
    );
    await expect(listResearches()).rejects.toMatchObject({ status: 0 });
  });
});

describe("parseValidationDetail", () => {
  it("returns an empty map for non-array details", () => {
    expect(parseValidationDetail("boom")).toEqual({});
  });
});

describe("validate", () => {
  it("requires title, objective and question", () => {
    expect(validate({ title: "", objective: "", question: "" })).toEqual({
      title: "Título é obrigatório.",
      objective: "Objetivo é obrigatório.",
      question: "Pergunta é obrigatória.",
    });
  });

  it("rejects titles longer than 200 characters", () => {
    const errors = validate({ title: "a".repeat(201), objective: "o", question: "q" });
    expect(errors.title).toContain("200");
  });

  it("accepts a valid payload", () => {
    expect(validate({ title: "ok", objective: "o", question: "q" })).toEqual({});
  });
});
