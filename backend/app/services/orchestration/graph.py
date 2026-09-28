"""LangGraph definition for the research workflow (RDA-033 / RDA-034).

    START -> planner -> search -> selection -> processing -> evidence
            -> validation -> synthesis -> complete | budget_exceeded | failed
            -> END

The state type is ResearchWorkflowState (RDA-032). Terminal routing depends
on the budget and on whether a permanent error was recorded. The validation
node (RDA-061) sits between evidence and synthesis to wire the
claim -> evidence -> source -> provenance -> validation chain.
"""

from langgraph.graph import END, START, StateGraph

from app.services.orchestration.nodes import ResearchNodes
from app.services.workflow.state import (
    ErrorSeverity,
    ResearchWorkflowState,
    WorkflowStage,
)


def route_after_synthesis(state: ResearchWorkflowState) -> str:
    """Decide the terminal stage after synthesis."""
    if state.budget.is_exceeded:
        return "budget_exceeded"
    if state.current_stage == WorkflowStage.FAILED:
        return "failed"
    if any(error.severity == ErrorSeverity.PERMANENT for error in state.errors):
        return "failed"
    return "complete"


def route_after_node(state: ResearchWorkflowState, next_node: str) -> str:
    """Stop at the budget terminal as soon as a node exhausts the budget."""
    if state.current_stage == WorkflowStage.BUDGET_EXCEEDED:
        return "budget_exceeded"
    # A node that ended FAILED (e.g. planning failed after retries) must stop
    # the pipeline: continuing would search/extract with no plan and could
    # even finish as COMPLETED when the recorded error was not PERMANENT.
    if state.current_stage == WorkflowStage.FAILED:
        return "failed"
    return next_node


def build_graph(nodes: ResearchNodes):
    """Build and compile the research workflow graph."""
    graph = StateGraph(ResearchWorkflowState)

    graph.add_node("planner", nodes.planner_node)
    graph.add_node("search", nodes.search_node)
    graph.add_node("selection", nodes.selection_node)
    graph.add_node("processing", nodes.processing_node)
    graph.add_node("evidence", nodes.evidence_node)
    graph.add_node("validation", nodes.validation_node)
    graph.add_node("synthesis", nodes.synthesis_node)
    graph.add_node("complete", nodes.complete_node)
    graph.add_node("budget_exceeded", nodes.budget_exceeded_node)
    graph.add_node("failed", nodes.failed_node)

    graph.add_edge(START, "planner")
    graph.add_conditional_edges(
        "planner", lambda state: route_after_node(state, "search"),
        {"search": "search", "budget_exceeded": "budget_exceeded", "failed": "failed"},
    )
    graph.add_conditional_edges(
        "search", lambda state: route_after_node(state, "selection"),
        {"selection": "selection", "budget_exceeded": "budget_exceeded", "failed": "failed"},
    )
    graph.add_conditional_edges(
        "selection", lambda state: route_after_node(state, "processing"),
        {"processing": "processing", "budget_exceeded": "budget_exceeded", "failed": "failed"},
    )
    graph.add_conditional_edges(
        "processing", lambda state: route_after_node(state, "evidence"),
        {"evidence": "evidence", "budget_exceeded": "budget_exceeded", "failed": "failed"},
    )
    graph.add_conditional_edges(
        "evidence", lambda state: route_after_node(state, "validation"),
        {"validation": "validation", "budget_exceeded": "budget_exceeded", "failed": "failed"},
    )
    graph.add_conditional_edges(
        "validation", lambda state: route_after_node(state, "synthesis"),
        {"synthesis": "synthesis", "budget_exceeded": "budget_exceeded", "failed": "failed"},
    )
    graph.add_conditional_edges(
        "synthesis",
        route_after_synthesis,
        {
            "complete": "complete",
            "budget_exceeded": "budget_exceeded",
            "failed": "failed",
        },
    )
    graph.add_edge("complete", END)
    graph.add_edge("budget_exceeded", END)
    graph.add_edge("failed", END)

    return graph.compile()
