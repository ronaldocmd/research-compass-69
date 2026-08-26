"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import type { ResearchDocument } from "@/types/document";

interface Props {
  researchId: string;
  documents: ResearchDocument[] | null;
}

type SortKey = "relevance" | "year" | "title";

function sortValue(document: ResearchDocument, key: SortKey): number | string {
  if (key === "title") return document.title.toLocaleLowerCase();
  if (key === "year") return document.publication_year ?? -Infinity;
  return document.relevance_score ?? -Infinity;
}

export function ResearchDocumentsView({ researchId, documents }: Props) {
  const [query, setQuery] = useState("");
  const [source, setSource] = useState("ALL");
  const [status, setStatus] = useState("ALL");
  const [sort, setSort] = useState<SortKey>("relevance");

  const sources = useMemo(() => [...new Set((documents ?? []).map((document) => document.source))].sort(), [documents]);
  const statuses = useMemo(() => [...new Set((documents ?? []).map((document) => document.status))].sort(), [documents]);
  const visibleDocuments = useMemo(() => {
    if (!documents) return [];
    const normalizedQuery = query.trim().toLocaleLowerCase();
    return documents
      .filter((document) => {
        const haystack = [document.title, ...document.authors].join(" ").toLocaleLowerCase();
        return (!normalizedQuery || haystack.includes(normalizedQuery))
          && (source === "ALL" || document.source === source)
          && (status === "ALL" || document.status === status);
      })
      .sort((left, right) => {
        const leftValue = sortValue(left, sort);
        const rightValue = sortValue(right, sort);
        return leftValue < rightValue ? 1 : leftValue > rightValue ? -1 : 0;
      });
  }, [documents, query, source, status, sort]);

  return (
    <main className="wide documents-page">
      <p className="breadcrumb"><Link href={`/researches/${researchId}/dashboard`}>← Dashboard</Link></p>
      <header className="documents-header">
        <div>
          <p className="eyebrow">Research workspace / documents</p>
          <h1>Documentos</h1>
          <p>As fontes encontradas para esta pesquisa, em um só lugar.</p>
        </div>
      </header>

      {documents === null ? (
        <div className="documents-unavailable">
          <span className="empty-mark" aria-hidden="true">DOCS / 00</span>
          <h2>A fonte de documentos ainda não está disponível</h2>
          <p>A API de documentos da pesquisa ainda não existe neste projeto. A tela está pronta para receber esses dados.</p>
          <Link href={`/researches/${researchId}/dashboard`} className="btn primary">Voltar ao dashboard</Link>
        </div>
      ) : documents.length === 0 ? (
        <div className="documents-unavailable compact">
          <h2>Nenhum documento encontrado</h2>
          <p>Esta pesquisa ainda não retornou documentos.</p>
        </div>
      ) : (
        <>
          <div className="documents-toolbar">
            <label className="search-field"><span className="search-icon" aria-hidden="true">/</span><span className="sr-only">Buscar documentos</span><input type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Buscar título ou autor" /></label>
            <select aria-label="Filtrar por fonte" value={source} onChange={(event) => setSource(event.target.value)}><option value="ALL">Todas as fontes</option>{sources.map((item) => <option key={item} value={item}>{item}</option>)}</select>
            <select aria-label="Filtrar por status" value={status} onChange={(event) => setStatus(event.target.value)}><option value="ALL">Todos os status</option>{statuses.map((item) => <option key={item} value={item}>{item}</option>)}</select>
            <select aria-label="Ordenar documentos" value={sort} onChange={(event) => setSort(event.target.value as SortKey)}><option value="relevance">Relevância</option><option value="year">Ano</option><option value="title">Título</option></select>
          </div>
          <div className="documents-list">
            {visibleDocuments.map((document) => (
              <article className="document-row" key={document.id}>
                <div className="document-main"><Link href={`/researches/${researchId}/documents/${document.id}`} className="document-title">{document.title}</Link><p>{document.authors.join(", ") || "Autores não informados"}</p></div>
                <span className="document-source">{document.source}</span>
                <span className="document-year">{document.publication_year ?? "N/A"}</span>
                <span className={`task-status ${document.status}`}>{document.status}</span>
                <div className="document-meta">{document.doi ? <a href={`https://doi.org/${document.doi}`} target="_blank" rel="noopener noreferrer">{document.doi}</a> : null}{document.relevance_score != null ? <small>{Math.round(document.relevance_score * 100)}% relevância</small> : null}</div>
              </article>
            ))}
          </div>
        </>
      )}
    </main>
  );
}