import { notFound } from "next/navigation";

import { ResearchDocumentDetail } from "@/components/ResearchDocumentDetail";
import { ApiError, getResearch } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function ResearchDocumentPage({ params }: { params: Promise<{ id: string; docId: string }> }) {
  const { id } = await params;
  try {
    const research = await getResearch(id);
    // TODO: add a document detail API helper when the backend exposes this resource.
    return <ResearchDocumentDetail researchId={research.id} document={null} />;
  } catch (error) {
    if (error instanceof ApiError && (error.isNotFound || error.isValidation)) notFound();
    throw error;
  }
}