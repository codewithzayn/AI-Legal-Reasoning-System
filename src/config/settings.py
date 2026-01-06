"""
Configuration settings for AI Legal Reasoning System
"""

# UI Configuration
APP_TITLE = "AI Legal Reasoning System"
APP_ICON = "⚖️"
CHAT_WELCOME_MESSAGE = "Tervetuloa! Ask me about Finnish legal documents."

# Streamlit Page Config
PAGE_CONFIG = {
    "page_title": APP_TITLE,
    "page_icon": APP_ICON,
    "layout": "centered",
    "initial_sidebar_state": "collapsed"
}

# Chat Configuration
MAX_CHAT_HISTORY = 50
USER_AVATAR = "👤"
ASSISTANT_AVATAR = "⚖️"
SYSTEM_STATUS = "🤖 LangGraph Agent Active"
