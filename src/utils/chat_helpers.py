"""
Helper functions for chat interface
"""

import streamlit as st
from typing import List, Dict


def initialize_chat_history() -> None:
    """Initialize chat history in session state if not exists"""
    if "messages" not in st.session_state:
        st.session_state.messages = []


def add_message(role: str, content: str) -> None:
    """
    Add a message to chat history
    
    Args:
        role: 'user' or 'assistant'
        content: Message text
    """
    st.session_state.messages.append({"role": role, "content": content})


def get_chat_history() -> List[Dict[str, str]]:
    """
    Get chat history from session state
    
    Returns:
        List of message dictionaries
    """
    return st.session_state.messages


def clear_chat_history() -> None:
    """Clear all chat history"""
    st.session_state.messages = []


def mock_assistant_response(user_input: str) -> str:
    """
    Mock assistant response (placeholder for LangGraph agent)
    
    Args:
        user_input: User's question
        
    Returns:
        Mock response string
    """
    return f"I received your question: '{user_input}'. LangGraph agent integration coming soon!"
