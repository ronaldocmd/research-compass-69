import { notFound } from "next/navigation";

import { ResearchDocumentsView } from "@/components/ResearchDocumentsView";
import { ApiError, getResearch, getResearchDocuments } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function ResearchDocumentsPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  try {
    const research = await getResearch(id);
    // TODO: add a documents API helper when the backend exposes this resource.
    const documents = await getResearchDocuments(id).catch(e => { if (e instanceof ApiError && e.isNotFound) return null; throw e; });
    return <ResearchDocumentsView researchId={research.id} documents={documents} />;
  } catch (error) {
    if (error instanceof ApiError && (error.isNotFound || error.isValidation)) notFound();
    throw error;
  }
}
