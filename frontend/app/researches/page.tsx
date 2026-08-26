import Link from "next/link";

import { ResearchDashboard } from "@/components/ResearchDashboard";
import { ApiError, listResearches } from "@/lib/api";
import type { Research } from "@/types/research";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "Pesquisas — Research Discovery Agent",
  description: "Dashboard de pesquisas: listar, criar, editar e excluir.",
};

export default async function ResearchesPage() {
  let researches: Research[] = [];
  let error: string | null = null;

  try {
    researches = await listResearches({ limit: 50, offset: 0 });
  } catch (err) {
    error = err instanceof ApiError ? err.message : "Erro inesperado ao carregar pesquisas.";
  }

  return (
    <main className="wide">
      <header className="row between">
        <div>
          <p className="eyebrow">Research workspace / 038</p>
          <h1>Pesquisas</h1>
          <p className="page-intro">Um lugar calmo para transformar perguntas em descobertas.</p>
        </div>
        <Link href="/researches/new" className="btn primary">
          Nova pesquisa
        </Link>
      </header>

      {error ? (
        <div className="card">
          <p className="alert">{error}</p>
          <p>Verifique se o backend FastAPI está em execução e se a URL da API está configurada.</p>
        </div>
      ) : (
        <ResearchDashboard researches={researches} />
      )}
    </main>
  );
}
