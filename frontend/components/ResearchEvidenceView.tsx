import Link from "next/link";

import type { ResearchEvidence } from "@/types/evidence";

interface Props {
  researchId: string;
  evidence: ResearchEvidence[] | null;
}

function value(value: string | number | null | undefined): string {
  return value == null || value === "" ? "N/A" : String(value);
}

export function ResearchEvidenceView({ researchId, evidence }: Props) {
  return (
    <main className="wide evidence-page">
      <div className="evidence-navigation">
        <Link href={`/researches/${researchId}/claims`}>← Claims</Link>
        <Link href={`/researches/${researchId}/dashboard`}>Dashboard</Link>
      </div>
      <header className="evidence-header">
        <div>
          <p className="eyebrow">Research workspace / evidence</p>
          <h1>Evidências</h1>
          <p>Trechos extraídos com o caminho de volta à fonte original.</p>
        </div>
      </header>

      {evidence === null ? (
        <div className="evidence-unavailable">
          <span className="empty-mark" aria-hidden="true">EVIDENCE / 00</span>
          <h2>A fonte de evidências ainda não está disponível</h2>
          <p>A API pública de evidências ainda não existe neste projeto. A view está preparada para exibir proveniência completa.</p>
          <Link href={`/researches/${researchId}/dashboard`} className="btn primary">Voltar ao dashboard</Link>
        </div>
      ) : evidence.length === 0 ? (
        <div className="evidence-unavailable compact"><h2>Nenhuma evidência encontrada</h2><p>Esta pesquisa ainda não retornou evidências.</p></div>
      ) : (
        <div className="evidence-list">
          {evidence.map((item) => (
            <article className="evidence-card" key={item.id}>
              <div className="evidence-card-top"><span className="claim-id">EVIDENCE / {item.id.slice(0, 8)}</span><span className={`validation-badge ${item.status}`}>{item.status}</span></div>
              <blockquote>{item.text || "N/A"}</blockquote>
              <dl className="provenance-grid">
                <div><dt>Documento</dt><dd>{item.document_id ? <Link href={`/researches/${researchId}/documents/${item.document_id}`}>{value(item.document_title)}</Link> : "N/A"}</dd></div>
                <div><dt>Fonte</dt><dd>{value(item.document_source)}</dd></div>
                <div><dt>Página</dt><dd>{value(item.page_number)}</dd></div>
                <div><dt>Seção</dt><dd>{value(item.section)}</dd></div>
                <div><dt>Chunk</dt><dd>{value(item.chunk_id)}</dd></div>
                <div><dt>Claim</dt><dd>{item.claim_id ? <Link href={`/researches/${researchId}/claims#${item.claim_id}`}>{value(item.claim_text)}</Link> : "N/A"}</dd></div>
              </dl>
            </article>
          ))}
        </div>
      )}
    </main>
  );
}