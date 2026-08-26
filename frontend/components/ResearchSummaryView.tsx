import Link from "next/link";

import type { Research } from "@/types/research";
import type { ResearchSummary } from "@/types/summary";

interface Props {
  research: Research;
  summary: ResearchSummary | null;
}

function sourceUrl(source: { doi?: string | null; url?: string | null }): string | null {
  return source.doi ? `https://doi.org/${source.doi}` : source.url ?? null;
}

export function ResearchSummaryView({ research, summary }: Props) {
  const discoveries = summary?.claims?.filter((claim) => claim.confidence != null && claim.confidence >= 0.7)
    .sort((left, right) => (right.confidence ?? 0) - (left.confidence ?? 0)) ?? [];
  const hasContent = Boolean(summary?.executive_summary || summary?.claims?.length || summary?.evidence?.length || summary?.sources?.length);

  return (
    <main className="wide summary-page">
      <div className="summary-navigation"><Link href={`/researches/${research.id}/dashboard`}>← Dashboard</Link><Link href={`/researches/${research.id}/plan`}>Plano</Link><Link href={`/researches/${research.id}/documents`}>Documentos</Link><Link href={`/researches/${research.id}/claims`}>Claims</Link><Link href={`/researches/${research.id}/evidence`}>Evidências</Link><Link href={`/researches/${research.id}/events`}>Eventos</Link></div>
      <header className="summary-header"><p className="eyebrow">Research workspace / summary</p><h1>{research.title}</h1><p>{research.question}</p></header>

      {!hasContent ? <div className="summary-incomplete"><strong>Esta pesquisa ainda está em andamento.</strong><span>O resumo será atualizado quando os dados consolidados do workflow estiverem disponíveis.</span></div> : null}

      {summary?.executive_summary ? <section className="summary-section executive-summary"><span className="section-label">Resumo executivo</span><p>{summary.executive_summary}</p></section> : null}
      {discoveries.length ? <section className="summary-section"><span className="section-label">Principais descobertas</span><div className="discovery-list">{discoveries.map((claim) => <article key={claim.id}><p>{claim.text}</p><small>{Math.round((claim.confidence ?? 0) * 100)}% de confiança · <Link href={`/researches/${research.id}/claims#${claim.id}`}>ver claim e evidências →</Link></small></article>)}</div></section> : null}
      {summary?.claims?.length ? <section className="summary-section"><div className="section-heading"><span className="section-label">Claims</span><Link href={`/researches/${research.id}/claims`}>Ver todos →</Link></div><p>{summary.claims.length} claims disponíveis.</p></section> : null}
      {summary?.evidence?.length ? <section className="summary-section"><div className="section-heading"><span className="section-label">Evidências</span><Link href={`/researches/${research.id}/evidence`}>Ver todas →</Link></div><p>{summary.evidence.length} evidências disponíveis.</p></section> : null}
      {summary?.limitations?.length ? <section className="summary-section"><span className="section-label">Limitações</span><ul>{summary.limitations.map((item) => <li key={item}>{item}</li>)}</ul></section> : null}
      {summary?.gaps?.length ? <section className="summary-section"><span className="section-label">Lacunas de pesquisa</span><ul>{summary.gaps.map((item) => <li key={item}>{item}</li>)}</ul></section> : null}
      {summary?.sources?.length ? <section className="summary-section"><span className="section-label">Fontes</span><div className="summary-sources">{summary.sources.map((source) => <article key={source.id}><Link href={`/researches/${research.id}/documents/${source.id}`}>{source.title}</Link><small>{source.authors.join(", ") || "Autores não informados"} · {source.publication_year ?? "N/A"}</small>{sourceUrl(source) ? <a href={sourceUrl(source) as string} target="_blank" rel="noopener noreferrer">Fonte original →</a> : null}</article>)}</div></section> : null}
    </main>
  );
}