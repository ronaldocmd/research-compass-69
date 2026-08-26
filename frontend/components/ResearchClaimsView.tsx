import Link from "next/link";

import type { ResearchClaim } from "@/types/claim";

interface Props {
  researchId: string;
  claims: ResearchClaim[] | null;
}

function confidenceTone(value: number): string {
  if (value >= 0.8) return "high";
  if (value >= 0.5) return "medium";
  return "low";
}

export function ResearchClaimsView({ researchId, claims }: Props) {
  return (
    <main className="wide claims-page">
      <p className="breadcrumb"><Link href={`/researches/${researchId}/dashboard`}>← Dashboard</Link></p>
      <header className="claims-header">
        <div>
          <p className="eyebrow">Research workspace / claims</p>
          <h1>Claims</h1>
          <p>Afirmações extraídas com rastreabilidade para suas fontes.</p>
        </div>
      </header>

      {claims === null ? (
        <div className="claims-unavailable">
          <span className="empty-mark" aria-hidden="true">CLAIMS / 00</span>
          <h2>A fonte de claims ainda não está disponível</h2>
          <p>A API pública de claims ainda não existe neste projeto. A view está preparada para receber texto, confiança, validação e evidências.</p>
          <Link href={`/researches/${researchId}/dashboard`} className="btn primary">Voltar ao dashboard</Link>
        </div>
      ) : claims.length === 0 ? (
        <div className="claims-unavailable compact"><h2>Nenhum claim encontrado</h2><p>Esta pesquisa ainda não retornou claims.</p></div>
      ) : (
        <div className="claims-list">
          {claims.map((claim) => (
            <article className="claim-card" key={claim.id}>
              <div className="claim-card-top"><span className="claim-id">CLAIM / {claim.id.slice(0, 8)}</span>{claim.validation_status ? <span className={`validation-badge ${claim.validation_status}`}>{claim.validation_status}</span> : null}</div>
              <p className="claim-text">{claim.text}</p>
              {claim.confidence != null ? <div className="confidence-line"><span>Confiança</span><strong className={confidenceTone(claim.confidence)}>{Math.round(claim.confidence * 100)}%</strong><div className="confidence-track"><span className={confidenceTone(claim.confidence)} style={{ width: `${Math.round(claim.confidence * 100)}%` }} /></div></div> : null}
              {claim.evidence?.length ? <div className="claim-evidence"><span className="section-label">Evidências relacionadas</span>{claim.evidence.slice(0, 3).map((evidence) => <Link href={`/researches/${researchId}/evidence/${evidence.id}`} key={evidence.id}>{evidence.text}<small>{evidence.document_title ?? "Documento não informado"}{evidence.page_number == null ? "" : ` · página ${evidence.page_number}`} →</small></Link>)}</div> : null}
              {claim.document_id ? <Link className="claim-document" href={`/researches/${researchId}/documents/${claim.document_id}`}>{claim.document_title ?? "Documento de origem"} →</Link> : null}
            </article>
          ))}
        </div>
      )}
    </main>
  );
}