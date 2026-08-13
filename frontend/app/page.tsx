import { getBackendHealth } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  const health = await getBackendHealth();

  return (
    <main>
      <h1>Research Discovery Agent</h1>
      <p>
        RDA-001 foundation. Backend: Python + FastAPI. Frontend: Next.js + TypeScript. Database:
        PostgreSQL via SQLAlchemy + Alembic.
      </p>
      <p>
        Backend status: <code>{health ? `${health.status} / db: ${health.database}` : "unreachable"}</code>
      </p>
    </main>
  );
}
