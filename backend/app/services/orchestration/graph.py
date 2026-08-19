"""LangGraph definition for the research workflow (RDA-033 / RDA-034).

    START -> planner -> search -> selection -> processing -> evidence
            -> synthesis -> complete | budget_exceeded | failed -> END

The state type is ResearchWorkflowState (RDA-032). Terminal routing depends
on the budget and on whether a permanent error was recorded.
"""

from langgraph.graph import END, START, StateGraph

from app.services.orchestration.nodes import ResearchNodes
from app.services.workflow.state import ErrorSeverity, ResearchWorkflowState


def route_after_synthesis(state: ResearchWorkflowState) -> str:
    """Decide the terminal stage after synthesis."""
    if state.budget.is_exceeded:
        return "budget_exceeded"
    if any(error.severity == ErrorSeverity.PERMANENT for error in state.errors):
        return "failed"
    return "complete"


def build_graph(nodes: ResearchNodes):
    """Build and compile the research workflow graph."""
    graph = StateGraph(ResearchWorkflowState)

    graph.add_node("planner", nodes.planner_node)
    graph.add_node("search", nodes.search_node)
    graph.add_node("selection", nodes.selection_node)
    graph.add_node("processing", nodes.processing_node)
    graph.add_node("evidence", nodes.evidence_node)
    graph.add_node("synthesis", nodes.synthesis_node)
    graph.add_node("complete", nodes.complete_node)
    graph.add_node("budget_exceeded", nodes.budget_exceeded_node)
    graph.add_node("failed", nodes.failed_node)

    graph.add_edge(START, "planner")
    graph.add_edge("planner", "search")
    graph.add_edge("search", "selection")
    graph.add_edge("selection", "processing")
    graph.add_edge("processing", "evidence")
    graph.add_edge("evidence", "synthesis")
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
