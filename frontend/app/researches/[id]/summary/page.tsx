import { notFound } from "next/navigation";

import { ResearchSummaryView } from "@/components/ResearchSummaryView";
import { ApiError, getResearch } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function ResearchSummaryPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  try {
    const research = await getResearch(id);
    // TODO: add summary API helper when the backend exposes consolidated results.
    return <ResearchSummaryView research={research} summary={null} />;
  } catch (error) {
    if (error instanceof ApiError && (error.isNotFound || error.isValidation)) notFound();
    throw error;
  }
}