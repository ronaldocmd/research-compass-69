import Link from "next/link";

import type { ResearchDocument } from "@/types/document";

interface Props {
  researchId: string;
  document: ResearchDocument | null;
}

function originalUrl(document: ResearchDocument): string | null {
  return document.doi ? `https://doi.org/${document.doi}` : document.url ?? null;
}

function display(value: string | number | null | undefined): string {
  return value == null || value === "" ? "N/A" : String(value);
}

export function ResearchDocumentDetail({ researchId, document }: Props) {
  const sourceLink = document ? originalUrl(document) : null;

  return (
    <main className="wide document-detail-page">
      <p className="breadcrumb"><Link href={`/researches/${researchId}/documents`}>← Documentos</Link></p>
      {!document ? (
        <section className="document-unavailable">
          <span className="empty-mark" aria-hidden="true">DOC / 00</span>
          <h1>Detalhe indisponível</h1>
          <p>A API de detalhe de documentos ainda não existe neste projeto.</p>
          <Link href={`/researches/${researchId}/dashboard`} className="btn primary">Voltar ao dashboard</Link>
        </section>
      ) : (
        <>
          <header className="document-detail-header">
            <div>
              <p className="eyebrow">Research workspace / document</p>
              <h1>{document.title}</h1>
              <p>{document.authors.join(", ") || "Autores não informados"}</p>
            </div>
            <span className={`task-status ${document.status}`}>{document.status}</span>
          </header>

          <section className="document-metadata">
            <div><span>Fonte</span><strong>{display(document.source)}</strong></div>
            <div><span>Ano</span><strong>{display(document.publication_year)}</strong></div>
            <div><span>Relevância</span><strong>{document.relevance_score == null ? "N/A" : `${Math.round(document.relevance_score * 100)}%`}</strong></div>
            <div><span>DOI</span><strong>{display(document.doi)}</strong></div>
          </section>

          {sourceLink ? <a className="original-source-link" href={sourceLink} target="_blank" rel="noopener noreferrer">Ver documento original →</a> : <p className="muted-note">Fonte original: N/A</p>}

          <section className="extracted-notice" role="note">
            <strong>Texto extraído automaticamente</strong>
            <span>O conteúdo abaixo foi extraído do documento original. Consulte sempre a fonte original para referências precisas.</span>
          </section>

          {document.abstract ? <section className="detail-section"><span className="section-label">Resumo</span><p>{document.abstract}</p></section> : null}
          {document.chunks?.length ? <section className="detail-section"><span className="section-label">Conteúdo extraído</span><div className="chunk-list">{document.chunks.map((chunk) => <article key={chunk.id}><small>{[chunk.section, chunk.page_number == null ? null : `página ${chunk.page_number}`].filter(Boolean).join(" · ") || "Trecho"}</small><p>{chunk.text}</p></article>)}</div></section> : null}
          {document.claims?.length ? <section className="detail-section"><span className="section-label">Claims relacionados</span><div className="related-list">{document.claims.map((claim) => <article key={claim.id}><p>{claim.text}</p><small>Confiança: {claim.confidence == null ? "N/A" : `${Math.round(claim.confidence * 100)}%`} · Página: {display(claim.page_number)}</small></article>)}</div></section> : null}
          {document.evidence?.length ? <section className="detail-section"><span className="section-label">Evidências relacionadas</span><div className="related-list">{document.evidence.map((item) => <article key={item.id}><p>“{item.text}”</p><small>{[item.section, item.page_number == null ? null : `página ${item.page_number}`].filter(Boolean).join(" · ") || "Referência não informada"}</small></article>)}</div></section> : null}
        </>
      )}
    </main>
  );
}