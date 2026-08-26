"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { ApiError, getWorkflowStatus } from "@/lib/api";
import type { Research } from "@/types/research";
import type { WorkflowStatus } from "@/types/workflow";

interface Props {
  research: Research;
  initialWorkflow: WorkflowStatus | null;
}

const stageProgress: Record<string, number> = {
  IDLE: 0, START: 0, PLANNING: 16, SEARCH: 33, SEARCHING: 33,
  SELECTING: 50, PROCESSING: 66, EXTRACTING: 78, VALIDATING: 88,
  SYNTHESIZING: 94, COMPLETED: 100, FAILED: 100, BUDGET_EXCEEDED: 100,
};

function count(value: unknown[] | undefined): string {
  return value ? String(value.length) : "N/A";
}

function formatMoney(value: number | undefined): string {
  return value == null ? "N/A" : `$${value.toFixed(3)}`;
}

function statusLabel(status: string): string {
  return status.replaceAll("_", " ").toLocaleLowerCase();
}

export function ResearchLiveDashboard({ research, initialWorkflow }: Props) {
  const [workflow, setWorkflow] = useState<WorkflowStatus | null>(initialWorkflow);
  const [refreshError, setRefreshError] = useState<string | null>(null);

  useEffect(() => {
    const refresh = async () => {
      try {
        setWorkflow(await getWorkflowStatus(research.id));
        setRefreshError(null);
      } catch (error) {
        if (!(error instanceof ApiError && error.isNotFound)) {
          setRefreshError("Atualização indisponível no momento.");
        }
      }
    };
    const timer = window.setInterval(refresh, 10000);
    return () => window.clearInterval(timer);
  }, [research.id]);

  const stage = workflow?.stage ?? workflow?.current_stage ?? research.status;
  const progress = stageProgress[stage] ?? null;
  const budget = workflow?.budget;
  const isTerminal = stage === "COMPLETED" || stage === "FAILED" || stage === "BUDGET_EXCEEDED";

  return (
    <main className="wide dashboard-page">
      <p className="breadcrumb"><Link href={`/researches/${research.id}`}>← Pesquisa</Link></p>
      <header className="dashboard-header">
        <div>
          <p className="eyebrow">Research workspace / live view</p>
          <h1>{research.title}</h1>
          <p className="dashboard-question">{research.question}</p>
        </div>
        <span className={`workflow-status ${statusLabel(stage)}`}>
          <span className="status-dot" />{statusLabel(stage)}
        </span>
      </header>

      <section className="dashboard-intro">
        <div>
          <span className="section-label">Objetivo</span>
          <p>{research.objective}</p>
        </div>
        <div className="progress-panel">
          <div className="progress-label"><span>Progresso</span><strong>{progress == null ? "N/A" : `${progress}%`}</strong></div>
          <div className="progress-track" aria-label={progress == null ? "Progresso não disponível" : `${progress}% concluído`}>
            {progress != null ? <span style={{ width: `${progress}%` }} /> : null}
          </div>
          {refreshError ? <small>{refreshError}</small> : <small>{isTerminal ? "Execução finalizada" : "Atualização automática a cada 10 segundos"}</small>}
        </div>
      </section>

      <section className="metrics-grid" aria-label="Métricas da pesquisa">
        <Metric label="Documentos encontrados" value={count(workflow?.search_results)} />
        <Metric label="Documentos processados" value={count(workflow?.processed_document_ids)} />
        <Metric label="Claims extraídos" value={count(workflow?.claims)} />
        <Metric label="Evidências" value={count(workflow?.evidence_items)} />
        <Metric label="Erros registrados" value={count(workflow?.errors)} />
        <Metric label="Custo estimado" value={formatMoney(budget?.estimated_cost_usd)} detail={budget?.total_tokens == null ? undefined : `${budget.total_tokens} tokens`} />
      </section>

      <section className="dashboard-lower-grid">
        <div className="dashboard-panel">
          <span className="section-label">Execução</span>
          <dl className="execution-list">
            <div><dt>Chamadas LLM</dt><dd>{budget?.llm_calls == null ? "N/A" : budget.llm_calls}</dd></div>
            <div><dt>Buscas</dt><dd>{budget?.search_calls == null ? "N/A" : budget.search_calls}</dd></div>
            <div><dt>Limite de custo</dt><dd>{formatMoney(budget?.max_cost_usd)}</dd></div>
          </dl>
        </div>
        <nav className="dashboard-panel dashboard-nav" aria-label="Navegação da pesquisa">
          <span className="section-label">Explorar</span>
          <Link href={`/researches/${research.id}`}>Visão geral <span>→</span></Link>
          <Link href={`/researches/${research.id}/plan`}>Plano <span>→</span></Link>
          <Link href={`/researches/${research.id}/documents`}>Documentos <span>→</span></Link>
          <Link href={`/researches/${research.id}/claims`}>Claims e evidências <span>→</span></Link>
          <Link href={`/researches/${research.id}/evidence`}>Evidence view <span>→</span></Link>
          <span className="nav-disabled">Resumo <small>Em breve</small></span>
        </nav>
      </section>
    </main>
  );
}

function Metric({ label, value, detail }: { label: string; value: string; detail?: string }) {
  return <div className="metric"><span>{label}</span><strong>{value}</strong>{detail ? <small>{detail}</small> : null}</div>;
}