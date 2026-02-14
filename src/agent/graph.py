"""
LangGraph Workflow Definition
Defines the agent's execution flow
"""

from typing import Literal

from langgraph.graph import END, StateGraph

from .nodes import (
    analyze_intent,
    ask_clarification,
    general_chat,
    generate_response,
    handle_error,
    reason_legal,
    reformulate_query,
    search_knowledge,
)
from .state import AgentState


def route_intent(state: AgentState) -> Literal["search", "chat", "clarify"]:
    """Route based on analysis intent"""
    intent = state.get("intent", "search")
    intent_map = {
        "legal_search": "search",
        "general_chat": "chat",
        "clarification": "clarify",
    }
    return intent_map.get(intent, "search")


def route_search_result(state: AgentState) -> Literal["reason", "reformulate"]:
    """Route based on search success"""
    results = state.get("search_results", [])
    attempts = state.get("search_attempts", 1)

    if results:
        # Found something -> Reason
        return "reason"

    if attempts >= 2:
        # Give up after 2 attempts → reason (will generate apology).
        # More retries just waste time when the DB cannot find matches.
        return "reason"

    # Formatting failed -> Try again
    return "reformulate"


def create_agent_graph() -> StateGraph:
    """
    Create the Autonomous LangGraph workflow
    """

    # Initialize graph
    workflow = StateGraph(AgentState)

    # Add nodes
    workflow.add_node("analyze", analyze_intent)
    workflow.add_node("search", search_knowledge)
    workflow.add_node("reason", reason_legal)
    workflow.add_node("reformulate", reformulate_query)
    workflow.add_node("clarify", ask_clarification)
    workflow.add_node("chat", general_chat)
    workflow.add_node("respond", generate_response)
    workflow.add_node("error", handle_error)

    # Define edges
    workflow.set_entry_point("analyze")

    # Conditional Edge: Analyze -> (Search | Chat | Clarify)
    workflow.add_conditional_edges("analyze", route_intent, {"search": "search", "chat": "chat", "clarify": "clarify"})

    # Conditional Edge: Search -> (Reason | Reformulate)
    workflow.add_conditional_edges("search", route_search_result, {"reason": "reason", "reformulate": "reformulate"})

    # Loop: Reformulate -> Search
    workflow.add_edge("reformulate", "search")

    # Linear edges: reason goes through respond; chat/clarify end directly (avoid duplicate response)
    workflow.add_edge("reason", "respond")
    workflow.add_edge("chat", END)
    workflow.add_edge("clarify", END)
    workflow.add_edge("respond", END)
    workflow.add_edge("error", END)

    return workflow


# Compile graph
agent_graph = create_agent_graph().compile()
