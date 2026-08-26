import Link from "next/link";
import { notFound } from "next/navigation";

import { DeleteResearchButton } from "@/components/DeleteResearchButton";
import { ApiError, getResearch } from "@/lib/api";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "Detalhe da pesquisa — Research Discovery Agent",
  description: "Visualizar, editar ou excluir uma pesquisa.",
};

export default async function ResearchDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;

  try {
    const research = await getResearch(id);

    return (
      <main className="wide">
        <p className="breadcrumb">
          <Link href="/researches">← Pesquisas</Link>
        </p>
        <header className="row between">
          <h1>{research.title}</h1>
          <span className={`badge ${research.status.toLowerCase()}`}>{research.status}</span>
        </header>

        <div className="card stack">
          <section>
            <h2>Objetivo</h2>
            <p>{research.objective}</p>
          </section>
          <section>
            <h2>Pergunta de pesquisa</h2>
            <p>{research.question}</p>
          </section>
          <dl className="meta">
            <div>
              <dt>ID</dt>
              <dd>
                <code>{research.id}</code>
              </dd>
            </div>
            <div>
              <dt>Criada em</dt>
              <dd>{new Date(research.created_at).toLocaleString("pt-BR")}</dd>
            </div>
            <div>
              <dt>Atualizada em</dt>
              <dd>{new Date(research.updated_at).toLocaleString("pt-BR")}</dd>
            </div>
          </dl>
          <div className="row">
            <Link href={`/researches/${research.id}/dashboard`} className="btn primary">
              Dashboard
            </Link>
            <Link href={`/researches/${research.id}/edit`} className="btn primary">
              Editar
            </Link>
            <DeleteResearchButton id={research.id} title={research.title} />
          </div>
        </div>
      </main>
    );
  } catch (error) {
    if (error instanceof ApiError && (error.isNotFound || error.isValidation)) notFound();
    return (
      <main className="wide">
        <p className="breadcrumb">
          <Link href="/researches">← Pesquisas</Link>
        </p>
        <div className="card">
          <p className="alert">
            {error instanceof ApiError ? error.message : "Erro inesperado ao carregar a pesquisa."}
          </p>
        </div>
      </main>
    );
  }
}
