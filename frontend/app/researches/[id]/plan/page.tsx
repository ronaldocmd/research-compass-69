import { notFound } from "next/navigation";

import { ResearchPlanView } from "@/components/ResearchPlanView";
import { ApiError, getResearch, getResearchPlan } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function ResearchPlanPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  try {
    const [research, plan] = await Promise.all([
      getResearch(id),
      getResearchPlan(id).catch((error) => {
        if (error instanceof ApiError && error.isNotFound) return null;
        throw error;
      }),
    ]);
    return <ResearchPlanView researchId={research.id} plan={plan} />;
  } catch (error) {
    if (error instanceof ApiError && (error.isNotFound || error.isValidation)) notFound();
    throw error;
  }
}