import { describe, expect, it } from "vitest";

import type { HealthResponse } from "../types/health";

describe("HealthResponse contract", () => {
  it("matches the backend schema shape", () => {
    const sample: HealthResponse = { status: "ok", database: "up", version: "0.1.0" };
    expect(Object.keys(sample).sort()).toEqual(["database", "status", "version"]);
  });
});
