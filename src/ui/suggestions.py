"""
Related question suggestions for LexAI.

Uses GPT-4o-mini to generate 3 follow-up questions based on the
last assistant response. Only generated for the most recent message
(cost control). Cached in session state.
"""

import os

import streamlit as st

from src.config.translations import t


def _generate_suggestions(query: str, response: str, lang: str) -> list[str]:
    """Call GPT-4o-mini to generate 3 follow-up questions."""
    try:
        from langchain_core.messages import HumanMessage, SystemMessage
        from langchain_openai import ChatOpenAI

        from src.config.settings import config

        llm = ChatOpenAI(
            model=config.OPENAI_SUPPORT_MODEL,
            temperature=0.7,
            max_tokens=200,
            api_key=os.getenv("OPENAI_API_KEY"),
            request_timeout=config.LLM_REQUEST_TIMEOUT,
        )

        lang_instruction = {
            "en": "Generate exactly 3 short follow-up questions in English.",
            "fi": "Luo tarkalleen 3 lyhytt\u00e4 jatkokysymyst\u00e4 suomeksi.",
            "sv": "Generera exakt 3 korta uppf\u00f6ljningsfr\u00e5gor p\u00e5 svenska.",
        }

        system = f"""You are a Finnish legal research assistant. Based on the user's question and the answer provided, suggest exactly 3 short follow-up questions that would help the user explore the topic further.
{lang_instruction.get(lang, lang_instruction["fi"])}
Output ONLY the 3 questions, one per line. No numbering, no bullets, no explanation."""

        result = llm.invoke(
            [
                SystemMessage(content=system),
                HumanMessage(content=f"Question: {query}\n\nAnswer summary: {response[:500]}"),
            ]
        )

        lines = [ln.strip().lstrip("0123456789.-) ") for ln in result.content.strip().splitlines() if ln.strip()]
        return lines[:3]
    except Exception:
        return []


def render_suggestions(query: str, response: str, lang: str, message_idx: int) -> None:
    """Render clickable follow-up question buttons for the last assistant message."""
    cache_key = f"suggestions_{message_idx}"

    # Generate suggestions if not cached
    if cache_key not in st.session_state:
        suggestions = _generate_suggestions(query, response, lang)
        st.session_state[cache_key] = suggestions

    suggestions = st.session_state.get(cache_key, [])
    if not suggestions:
        return

    st.caption(f"\U0001f4a1 {t('related_questions', lang)}")
    for i, suggestion in enumerate(suggestions):
        if st.button(
            f"\u2192 {suggestion}",
            key=f"suggestion_{message_idx}_{i}",
            use_container_width=True,
            type="secondary",
        ):
            st.session_state.pending_template = suggestion
            st.session_state.scroll_to_bottom = True
            st.rerun()
