"""
Helper functions for chat interface
"""

import streamlit as st
import sys
from pathlib import Path
from typing import List, Dict

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent.parent))

from src.agent.agent import process_query


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


def get_agent_response(user_input: str) -> str:
    """
    Get response from LangGraph agent
    
    Args:
        user_input: User's question
        
    Returns:
        Agent's response string
    """
    # Get chat history for context
    chat_history = get_chat_history()
    # Process through LangGraph agent
    response = process_query(user_input, chat_history)
    
    return response
