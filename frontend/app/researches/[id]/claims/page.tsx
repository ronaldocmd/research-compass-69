import { notFound } from "next/navigation";

import { ResearchClaimsView } from "@/components/ResearchClaimsView";
import { ApiError, getResearch } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function ResearchClaimsPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  try {
    const research = await getResearch(id);
    // TODO: add a claims API helper when the backend exposes this resource.
    return <ResearchClaimsView researchId={research.id} claims={null} />;
  } catch (error) {
    if (error instanceof ApiError && (error.isNotFound || error.isValidation)) notFound();
    throw error;
  }
}