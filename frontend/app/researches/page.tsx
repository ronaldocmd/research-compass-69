import Link from "next/link";

import { ApiError, listResearches } from "@/lib/api";
import type { Research } from "@/types/research";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "Pesquisas — Research Discovery Agent",
  description: "Dashboard de pesquisas: listar, criar, editar e excluir.",
};

function formatDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString("pt-BR");
}

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
          <h1>Pesquisas</h1>
          <p>Dashboard conectado à Research API (/api/v1/researches).</p>
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
      ) : researches.length === 0 ? (
        <div className="card empty">
          <p>Nenhuma pesquisa cadastrada ainda.</p>
          <Link href="/researches/new" className="btn primary">
            Criar a primeira pesquisa
          </Link>
        </div>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>Título</th>
              <th>Status</th>
              <th>Criada em</th>
              <th>Ações</th>
            </tr>
          </thead>
          <tbody>
            {researches.map((research) => (
              <tr key={research.id}>
                <td>
                  <Link href={`/researches/${research.id}`}>{research.title}</Link>
                </td>
                <td>
                  <span className={`badge ${research.status.toLowerCase()}`}>{research.status}</span>
                </td>
                <td>{formatDate(research.created_at)}</td>
                <td className="row">
                  <Link href={`/researches/${research.id}`} className="btn">
                    Detalhe
                  </Link>
                  <Link href={`/researches/${research.id}/edit`} className="btn">
                    Editar
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </main>
  );
}
