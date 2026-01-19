"""
LangGraph Workflow Definition
Defines the agent's execution flow
"""

from langgraph.graph import StateGraph, END
from .state import AgentState
from .nodes import (
    search_knowledge,
    reason_legal,
    generate_response,
    handle_error
)


def create_agent_graph() -> StateGraph:
    """
    Create the LangGraph workflow
    
    Flow:
    User Query → Search → Reason → Respond
    """
    
    # Initialize graph
    workflow = StateGraph(AgentState)
    
    # Add nodes (processing stages)
    workflow.add_node("search", search_knowledge)
    workflow.add_node("reason", reason_legal)
    workflow.add_node("respond", generate_response)
    workflow.add_node("error", handle_error)
    
    # Define edges (workflow flow)
    workflow.set_entry_point("search")
    workflow.add_edge("search", "reason")
    workflow.add_edge("reason", "respond")
    workflow.add_edge("respond", END)
    workflow.add_edge("error", END)
    
    return workflow


# Compile graph
agent_graph = create_agent_graph().compile()
