import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Research Discovery Agent — RDA-001 Foundation" },
      {
        name: "description",
        content:
          "RDA-001 executable foundation: FastAPI backend, Next.js frontend, PostgreSQL with SQLAlchemy and Alembic, orchestrated by Docker Compose.",
      },
      { property: "og:title", content: "Research Discovery Agent — RDA-001 Foundation" },
      {
        property: "og:description",
        content:
          "Monorepo foundation for the Research Discovery Agent MVP: FastAPI, Next.js, PostgreSQL, Docker Compose.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: Index,
});

const stack = [
  { layer: "Backend", value: "Python 3.12 + FastAPI" },
  { layer: "Frontend", value: "Next.js 15 + TypeScript (App Router)" },
  { layer: "Database", value: "PostgreSQL 16 + SQLAlchemy 2.0 + Alembic" },
  { layer: "Runtime", value: "Docker Compose" },
];

const endpoints = [
  { path: "http://localhost:3000", label: "Next.js frontend" },
  { path: "http://localhost:8000/docs", label: "API docs" },
  { path: "http://localhost:8000/health", label: "Liveness probe" },
  { path: "http://localhost:8000/api/v1/health", label: "DB-aware health" },
];

function Index() {
  return (
    <main className="min-h-screen bg-background px-6 py-16 text-foreground">
      <div className="mx-auto max-w-3xl">
        <p className="text-xs font-medium uppercase tracking-[0.2em] text-muted-foreground">
          Sprint 1 · RDA-001
        </p>
        <h1 className="mt-3 text-4xl font-semibold tracking-tight">Research Discovery Agent</h1>
        <p className="mt-4 text-base leading-relaxed text-muted-foreground">
          Executable monorepo foundation. Architecture flow is strictly API → Service → Repository →
          Database. Agents, search, PDFs, embeddings, LangGraph, Redis and Research CRUD are out of
          scope for this sprint.
        </p>

        <section className="mt-10">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
            Stack
          </h2>
          <dl className="mt-4 divide-y divide-border rounded-lg border border-border">
            {stack.map((row) => (
              <div key={row.layer} className="flex flex-wrap gap-2 px-4 py-3 text-sm">
                <dt className="w-24 font-medium">{row.layer}</dt>
                <dd className="text-muted-foreground">{row.value}</dd>
              </div>
            ))}
          </dl>
        </section>

        <section className="mt-10">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
            Local endpoints
          </h2>
          <ul className="mt-4 space-y-2 text-sm">
            {endpoints.map((e) => (
              <li key={e.path} className="flex flex-wrap items-baseline gap-2">
                <code className="rounded bg-muted px-2 py-1 text-xs">{e.path}</code>
                <span className="text-muted-foreground">{e.label}</span>
              </li>
            ))}
          </ul>
        </section>

        <section className="mt-10">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
            Run
          </h2>
          <pre className="mt-4 overflow-x-auto rounded-lg border border-border bg-muted p-4 text-xs leading-relaxed">
            {`cp .env.example .env\ndocker compose up --build`}
          </pre>
          <p className="mt-3 text-sm text-muted-foreground">
            This in-browser preview is a static shell for the RDA-001 foundation. The FastAPI,
            Next.js and PostgreSQL services run through Docker Compose on your machine.
          </p>
        </section>
      </div>
    </main>
  );
}
