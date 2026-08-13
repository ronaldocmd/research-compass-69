import { defineTool } from "@lovable.dev/mcp-js";

const stack = {
  project: "Research Discovery Agent (RDA)",
  sprint: "Sprint 1 — executable foundation",
  backend: {
    language: "Python 3.12",
    framework: "FastAPI",
    layering: "API -> Service -> Repository -> Database",
    orm: "SQLAlchemy 2.x",
    migrations: "Alembic",
    healthEndpoints: [
      { path: "/health", purpose: "liveness, independent of the database" },
      { path: "/api/v1/health", purpose: "health check that pings PostgreSQL" },
    ],
  },
  frontend: { framework: "Next.js", language: "TypeScript" },
  database: { engine: "PostgreSQL 16", container: "postgres:16-alpine", volume: "postgres_data" },
  orchestration: {
    tool: "Docker Compose",
    services: ["postgres", "backend", "frontend"],
    network: "rda-net (bridge)",
  },
  domainModel: {
    table: "researches",
    fields: ["id (uuid)", "title (varchar 200)", "objective (text)", "question (text)", "status", "created_at", "updated_at"],
    status: ["DRAFT", "READY"],
  },
  notImplementedYet: [
    "Research CRUD (RDA-006+)",
    "search",
    "PDF ingestion",
    "embeddings",
    "Redis",
    "LangGraph / agents",
  ],
};

export default defineTool({
  name: "get_project_stack",
  title: "Get project stack",
  description:
    "Describe the Research Discovery Agent architecture: backend, frontend, database, Docker services, health endpoints and current scope boundaries.",
  inputSchema: {},
  annotations: { readOnlyHint: true, idempotentHint: true, openWorldHint: false },
  handler: () => ({
    content: [{ type: "text" as const, text: JSON.stringify(stack, null, 2) }],
    structuredContent: stack,
  }),
});
