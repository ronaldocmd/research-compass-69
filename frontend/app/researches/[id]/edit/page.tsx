import Link from "next/link";
import { notFound } from "next/navigation";

import { ResearchForm } from "@/components/ResearchForm";
import { ApiError, getResearch } from "@/lib/api";
import { updateResearchAction } from "@/lib/research-actions";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "Editar pesquisa — Research Discovery Agent",
  description: "Atualizar título, objetivo, pergunta e status de uma pesquisa.",
};

export default async function EditResearchPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;

  try {
    const research = await getResearch(id);
    return (
      <main className="wide">
        <p className="breadcrumb">
          <Link href={`/researches/${research.id}`}>← Detalhe</Link>
        </p>
        <h1>Editar pesquisa</h1>
        <ResearchForm
          action={updateResearchAction}
          research={research}
          submitLabel="Salvar alterações"
          cancelHref={`/researches/${research.id}`}
        />
      </main>
    );
  } catch (error) {
    if (error instanceof ApiError && (error.isNotFound || error.isValidation)) notFound();
    throw error;
  }
}
