import { notFound } from "next/navigation";

import { ResearchSummaryView } from "@/components/ResearchSummaryView";
import { ApiError, getResearch } from "@/lib/api";
import type { ResearchSummary } from "@/types/summary";

export const dynamic = "force-dynamic";

export default async function ResearchSummaryPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  try {
    const research = await getResearch(id);
    // RDA-065: the backend now exposes the synthesis summary on the research
    // resource. Surface it as the executive summary so the generated findings
    // are actually visible instead of the "still in progress" placeholder.
    const summary: ResearchSummary | null = research.summary
      ? { executive_summary: research.summary }
      : null;
    return <ResearchSummaryView research={research} summary={summary} />;
  } catch (error) {
    if (error instanceof ApiError && (error.isNotFound || error.isValidation)) notFound();
    throw error;
  }
}