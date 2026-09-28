import { notFound } from "next/navigation";

import { ResearchClaimsView } from "@/components/ResearchClaimsView";
import { ApiError, getResearch, getResearchClaims } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function ResearchClaimsPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  try {
    const research = await getResearch(id);
    // TODO: add a claims API helper when the backend exposes this resource.
    const claims = await getResearchClaims(id).catch(e => { if (e instanceof ApiError && e.isNotFound) return null; throw e; });
    return <ResearchClaimsView researchId={research.id} claims={claims} />;
  } catch (error) {
    if (error instanceof ApiError && (error.isNotFound || error.isValidation)) notFound();
    throw error;
  }
}
