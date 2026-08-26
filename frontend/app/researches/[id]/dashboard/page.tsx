import { notFound } from "next/navigation";

import { ResearchLiveDashboard } from "@/components/ResearchLiveDashboard";
import { ApiError, getResearch, getWorkflowStatus } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function ResearchDashboardPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  try {
    const [research, workflow] = await Promise.all([
      getResearch(id),
      getWorkflowStatus(id).catch((error) => {
        if (error instanceof ApiError && error.isNotFound) return null;
        throw error;
      }),
    ]);
    return <ResearchLiveDashboard research={research} initialWorkflow={workflow} />;
  } catch (error) {
    if (error instanceof ApiError && (error.isNotFound || error.isValidation)) notFound();
    throw error;
  }
}