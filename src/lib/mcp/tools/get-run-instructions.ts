import { defineTool } from "@lovable.dev/mcp-js";
import { z } from "zod";

const instructions = {
  steps: [
    "cp .env.example .env",
    "docker compose up --build -d",
    "docker compose exec backend alembic upgrade head",
    "docker compose exec backend pytest",
  ],
  urls: {
    frontend: "http://localhost:3000",
    backendLiveness: "http://localhost:8000/health",
    backendHealth: "http://localhost:8000/api/v1/health",
    openapi: "http://localhost:8000/docs",
    postgres: "localhost:5432",
  },
  notes: [
    "All credentials come from environment variables; no secrets are committed.",
    "The Lovable preview renders a status page only — the Docker/Python/Next.js services run locally.",
  ],
};

export default defineTool({
  name: "get_run_instructions",
  title: "Get local run instructions",
  description:
    "Return the commands and local URLs needed to run the Research Discovery Agent stack with Docker Compose.",
  inputSchema: {},
  outputSchema: {
    steps: z.array(z.string()),
    urls: z.unknown(),
    notes: z.array(z.string()),
  },
  annotations: { readOnlyHint: true, idempotentHint: true, openWorldHint: false },
  handler: () => ({
    content: [{ type: "text" as const, text: JSON.stringify(instructions, null, 2) }],
    structuredContent: instructions,
  }),
});
