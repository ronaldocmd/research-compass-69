import Link from "next/link";

import type { PlanTask, ResearchPlan } from "@/types/plan";

interface Props {
  researchId: string;
  plan: ResearchPlan | null;
}

function statusLabel(value: string): string {
  return value.replaceAll("_", " ").toLocaleLowerCase();
}

function priorityTone(priority: number): string {
  if (priority <= 1) return "high";
  if (priority === 2) return "medium";
  return "low";
}

function TaskRow({ task }: { task: PlanTask }) {
  return (
    <li className="plan-task">
      <div className="task-index">{String(task.order + 1).padStart(2, "0")}</div>
      <div className="task-content">
        <div className="task-heading">
          <h2>{task.title}</h2>
          <span className={`priority-badge ${priorityTone(task.priority)}`}>P{task.priority}</span>
        </div>
        <p>{task.description}</p>
        {task.result_summary ? <small className="task-result">Resultado: {task.result_summary}</small> : null}
        {task.error_message ? <small className="task-error">{task.error_message}</small> : null}
      </div>
      <span className={`task-status ${statusLabel(task.status)}`}>{statusLabel(task.status)}</span>
    </li>
  );
}

export function ResearchPlanView({ researchId, plan }: Props) {
  if (!plan) {
    return (
      <main className="wide plan-page">
        <p className="breadcrumb"><Link href={`/researches/${researchId}/dashboard`}>← Dashboard</Link></p>
        <div className="plan-empty">
          <span className="empty-mark" aria-hidden="true">PLAN / 00</span>
          <h1>O plano ainda não foi gerado</h1>
          <p>Quando o Planner criar uma sequência de trabalho, ela aparecerá aqui.</p>
          <Link href={`/researches/${researchId}/dashboard`} className="btn primary">Voltar ao dashboard</Link>
        </div>
      </main>
    );
  }

  const completed = plan.tasks.filter((task) => task.status === "COMPLETED").length;
  const progress = plan.tasks.length ? Math.round((completed / plan.tasks.length) * 100) : 0;

  return (
    <main className="wide plan-page">
      <p className="breadcrumb"><Link href={`/researches/${researchId}/dashboard`}>← Dashboard</Link></p>
      <header className="plan-header">
        <div>
          <p className="eyebrow">Research workspace / plan</p>
          <h1>Plano de pesquisa</h1>
          <p>Uma sequência legível do trabalho que o RDA está executando.</p>
        </div>
        <span className={`workflow-status ${statusLabel(plan.status)}`}><span className="status-dot" />{statusLabel(plan.status)}</span>
      </header>

      <section className="plan-progress" aria-label="Progresso do plano">
        <div className="progress-label"><span>Progresso geral</span><strong>{completed}/{plan.tasks.length} concluídas</strong></div>
        <div className="progress-track"><span style={{ width: `${progress}%` }} /></div>
        <small>{progress}% do plano concluído</small>
      </section>

      {plan.tasks.length === 0 ? (
        <div className="plan-empty compact"><h2>O plano está sem tarefas</h2><p>Nenhuma task foi retornada pela API.</p></div>
      ) : (
        <ol className="plan-task-list">{plan.tasks.map((task) => <TaskRow key={task.id} task={task} />)}</ol>
      )}
    </main>
  );
}