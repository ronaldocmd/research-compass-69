import Link from "next/link";

import type { ResearchEvent } from "@/types/event";

interface Props {
  researchId: string;
  events: ResearchEvent[] | null;
  active?: boolean;
}

const eventLabels: Record<ResearchEvent["event_type"], string> = {
  planning: "Planejamento",
  search: "Busca",
  document: "Documento",
  processing: "Processamento",
  evidence: "Evidência",
  synthesis: "Síntese",
  error: "Erro",
  budget: "Budget",
};

function formatTimestamp(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString("pt-BR");
}

export function ResearchEventsView({ researchId, events, active = false }: Props) {
  return (
    <main className="wide events-page">
      <p className="breadcrumb"><Link href={`/researches/${researchId}/dashboard`}>← Dashboard</Link></p>
      <header className="events-header">
        <div>
          <p className="eyebrow">Research workspace / events</p>
          <h1>Progresso</h1>
          <p>O histórico da execução, em ordem cronológica.</p>
        </div>
        {active ? <span className="live-indicator"><span className="status-dot" />Em execução</span> : null}
      </header>

      {events === null ? (
        <div className="events-unavailable">
          <span className="empty-mark" aria-hidden="true">EVENTS / 00</span>
          <h2>O histórico de eventos ainda não está disponível</h2>
          <p>O backend ainda não expõe SSE nem um histórico de eventos para esta pesquisa. O feed será preenchido quando esse mecanismo existir.</p>
          <Link href={`/researches/${researchId}/dashboard`} className="btn primary">Voltar ao dashboard</Link>
        </div>
      ) : events.length === 0 ? (
        <div className="events-unavailable compact"><h2>Nenhum evento registrado</h2><p>A execução ainda não produziu eventos.</p></div>
      ) : (
        <ol className="event-list">
          {events.map((event) => <li className={`event-row ${event.event_type === "error" ? "event-error" : ""}`} key={event.id}><span className="event-marker">{eventLabels[event.event_type]}</span><div><p>{event.message}</p><small>{formatTimestamp(event.timestamp)}</small></div></li>)}
        </ol>
      )}
    </main>
  );
}