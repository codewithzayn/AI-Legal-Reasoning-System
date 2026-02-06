"""
Helper functions for chat interface
"""

import streamlit as st


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


def get_chat_history() -> list[dict[str, str]]:
    """
    Get chat history from session state

    Returns:
        List of message dictionaries
    """
    return st.session_state.messages


def clear_chat_history() -> None:
    """Clear all chat history"""
    st.session_state.messages = []
