"""
Streamlit Chat Interface for AI Legal Reasoning System
"""

import streamlit as st
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from config.settings import PAGE_CONFIG, APP_TITLE, CHAT_WELCOME_MESSAGE, USER_AVATAR, ASSISTANT_AVATAR
from utils.chat_helpers import (
    initialize_chat_history,
    add_message,
    get_chat_history,
    clear_chat_history,
    mock_assistant_response
)


def main():
    """Main Streamlit application"""
    
    # Configure page
    st.set_page_config(**PAGE_CONFIG)
    
    # App header
    st.title(APP_TITLE)
    st.markdown("""
        <div style='background: linear-gradient(90deg, #1f77b4 0%, #2ca02c 100%); 
                    padding: 1rem; 
                    border-radius: 0.5rem; 
                    margin-bottom: 1rem;'>
            <h3 style='color: white; margin: 0; text-align: center;'>
                🇫🇮 Finnish Legal Document Analysis System
            </h3>
            <p style='color: #e0e0e0; margin: 0.5rem 0 0 0; text-align: center; font-size: 0.9rem;'>
                AI-powered legal reasoning for Finnish statutes, case law, and regulations
            </p>
        </div>
    """, unsafe_allow_html=True)
    
    # Initialize chat history
    initialize_chat_history()
    
    # Display chat history
    for message in get_chat_history():
        avatar = USER_AVATAR if message["role"] == "user" else ASSISTANT_AVATAR
        with st.chat_message(message["role"], avatar=avatar):
            st.write(message["content"])
    
    # Chat input
    if prompt := st.chat_input(CHAT_WELCOME_MESSAGE):
        # Add user message
        add_message("user", prompt)
        with st.chat_message("user", avatar=USER_AVATAR):
            st.write(prompt)
        
        # Generate assistant response (mock for now)
        with st.chat_message("assistant", avatar=ASSISTANT_AVATAR):
            with st.spinner("Processing..."):
                response = mock_assistant_response(prompt)
                st.write(response)
        
        # Add assistant message
        add_message("assistant", response)
    
    # Sidebar (moved to end for accurate count)
    with st.sidebar:
        st.header("Settings")
        if st.button("Clear Chat History", use_container_width=True):
            clear_chat_history()
            st.rerun()
        
        st.divider()
        st.subheader("System Info")
        st.info(f"📊 Messages: {len(get_chat_history())}")
        st.info("🔧 Status: UI Only (LangGraph pending)")


if __name__ == "__main__":
    main()
