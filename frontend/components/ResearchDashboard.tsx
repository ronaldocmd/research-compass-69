"use client";

import Link from "next/link";
import { useState } from "react";

import type { Research } from "@/types/research";

interface Props {
  researches: Research[];
}

function formatDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleDateString("pt-BR", { day: "2-digit", month: "short", year: "numeric" });
}

export function ResearchDashboard({ researches }: Props) {
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<"ALL" | "READY" | "DRAFT">("ALL");
  const normalizedQuery = query.trim().toLocaleLowerCase();
  const visibleResearches = researches.filter((research) => {
    const matchesFilter = filter === "ALL" || research.status === filter;
    const matchesQuery = !normalizedQuery || [research.title, research.objective, research.question]
      .join(" ")
      .toLocaleLowerCase()
      .includes(normalizedQuery);
    return matchesFilter && matchesQuery;
  });

  return (
    <section className="dashboard-shell" aria-label="Painel de pesquisas">
      <div className="dashboard-toolbar">
        <label className="search-field">
          <span className="search-icon" aria-hidden="true">/</span>
          <span className="sr-only">Buscar pesquisas</span>
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Buscar por título, objetivo ou pergunta"
            type="search"
          />
        </label>
        <div className="filter-tabs" role="group" aria-label="Filtrar por status">
          {(["ALL", "READY", "DRAFT"] as const).map((value) => (
            <button
              className={filter === value ? "filter-tab active" : "filter-tab"}
              key={value}
              onClick={() => setFilter(value)}
              type="button"
            >
              {value === "ALL" ? "Todas" : value === "READY" ? "Prontas" : "Rascunhos"}
            </button>
          ))}
        </div>
      </div>

      {visibleResearches.length === 0 ? (
        <div className="dashboard-empty">
          <span className="empty-mark" aria-hidden="true">00</span>
          <h2>{researches.length === 0 ? "Seu espaço de pesquisa está vazio" : "Nenhum resultado encontrado"}</h2>
          <p>
            {researches.length === 0
              ? "Comece registrando uma pergunta. O restante da descoberta acontece aqui."
              : "Tente outra busca ou ajuste o filtro de status."}
          </p>
          {researches.length === 0 ? (
            <Link href="/researches/new" className="btn primary">Criar pesquisa</Link>
          ) : null}
        </div>
      ) : (
        <div className="research-table-wrap">
          <table className="research-table">
            <thead>
              <tr>
                <th>Pesquisa</th>
                <th>Status</th>
                <th>Atualizada</th>
                <th><span className="sr-only">Ações</span></th>
              </tr>
            </thead>
            <tbody>
              {visibleResearches.map((research) => (
                <tr key={research.id}>
                  <td className="research-title-cell">
                    <Link href={`/researches/${research.id}`}>{research.title}</Link>
                    <span>{research.question}</span>
                  </td>
                  <td><span className={`status-dot ${research.status.toLowerCase()}`} />{research.status === "READY" ? "Pronta" : "Rascunho"}</td>
                  <td className="date-cell">{formatDate(research.updated_at)}</td>
                  <td className="action-cell">
                    <Link href={`/researches/${research.id}`} className="table-action">Abrir</Link>
                    <Link href={`/researches/${research.id}/edit`} className="table-action">Editar</Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="result-count">{visibleResearches.length} de {researches.length} pesquisas</p>
        </div>
      )}
    </section>
  );
}