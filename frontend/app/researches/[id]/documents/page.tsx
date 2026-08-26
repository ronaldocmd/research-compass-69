import { notFound } from "next/navigation";

import { ResearchDocumentsView } from "@/components/ResearchDocumentsView";
import { ApiError, getResearch } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function ResearchDocumentsPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  try {
    const research = await getResearch(id);
    // TODO: add a documents API helper when the backend exposes this resource.
    return <ResearchDocumentsView researchId={research.id} documents={null} />;
  } catch (error) {
    if (error instanceof ApiError && (error.isNotFound || error.isValidation)) notFound();
    throw error;
  }
}