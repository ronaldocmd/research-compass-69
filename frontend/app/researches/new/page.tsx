import Link from "next/link";

import { ResearchForm } from "@/components/ResearchForm";
import { createResearchAction } from "@/lib/research-actions";

export const metadata = {
  title: "Nova pesquisa — Research Discovery Agent",
  description: "Criar uma nova pesquisa através da Research API.",
};

export default function NewResearchPage() {
  return (
    <main className="wide">
      <p className="breadcrumb">
        <Link href="/researches">← Pesquisas</Link>
      </p>
      <h1>Nova pesquisa</h1>
      <ResearchForm
        action={createResearchAction}
        submitLabel="Criar pesquisa"
        cancelHref="/researches"
      />
    </main>
  );
}
