import { notFound } from "next/navigation";

import { ResearchEvidenceView } from "@/components/ResearchEvidenceView";
import { ApiError, getResearch } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function ResearchEvidencePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  try {
    const research = await getResearch(id);
    // TODO: add an evidence API helper when the backend exposes this resource.
    return <ResearchEvidenceView researchId={research.id} evidence={null} />;
  } catch (error) {
    if (error instanceof ApiError && (error.isNotFound || error.isValidation)) notFound();
    throw error;
  }
}