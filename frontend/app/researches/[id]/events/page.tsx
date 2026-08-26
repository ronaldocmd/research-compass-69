import { notFound } from "next/navigation";

import { ResearchEventsView } from "@/components/ResearchEventsView";
import { ApiError, getResearch } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function ResearchEventsPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  try {
    const research = await getResearch(id);
    // TODO: add SSE or event-history helper when the backend exposes it.
    return <ResearchEventsView researchId={research.id} events={null} active={false} />;
  } catch (error) {
    if (error instanceof ApiError && (error.isNotFound || error.isValidation)) notFound();
    throw error;
  }
}