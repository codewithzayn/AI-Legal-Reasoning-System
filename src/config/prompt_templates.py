"""
Editable prompt templates for the chat UI.
Lawyers can click a template to use it as their question.
Edit this file to add or change suggested prompts.
"""

# Each template has: label (shown on button) and prompt (sent when clicked)
# Keys: "en", "fi", "sv" for language. Use same keys as translations.
PROMPT_TEMPLATES: dict[str, list[dict[str, str]]] = {
    "en": [
        {"label": "Find cases about fraud", "prompt": "Find cases about fraud"},
        {"label": "Tell me about insurance contracts", "prompt": "Tell me about insurance contracts"},
        {"label": "What is the penalty for theft?", "prompt": "What is the penalty for theft (varkaus)?"},
        {"label": "Summarize a specific case", "prompt": "Summarize case KKO:2024:76"},
        {"label": "Civil courts and jurisdiction", "prompt": "Tell me about civil courts"},
    ],
    "fi": [
        {"label": "Etsi tapauksia petoksesta", "prompt": "Etsi tapauksia petoksesta"},
        {"label": "Kerro vakuutussopimuksista", "prompt": "Kerro vakuutussopimuksista"},
        {"label": "Mikä on varkauden rangaistus?", "prompt": "Mikä on varkauden (varkaus) rangaistus?"},
        {"label": "Tiivistä tietty tapaus", "prompt": "Tiivistä tapaus KKO:2024:76"},
        {"label": "Siviilioikeudet ja toimivalta", "prompt": "Kerro siviilioikeuksista"},
    ],
    "sv": [
        {"label": "Hitta fall om bedrägeri", "prompt": "Hitta fall om bedrägeri"},
        {"label": "Berätta om försäkringsavtal", "prompt": "Berätta om försäkringsavtal"},
        {"label": "Vad är straffet för stöld?", "prompt": "Vad är straffet för stöld (varkaus)?"},
        {"label": "Sammanfatta ett specifikt fall", "prompt": "Sammanfatta fall KKO:2024:76"},
        {"label": "Civila domstolar och jurisdiktion", "prompt": "Berätta om civila domstolar"},
    ],
}


def get_templates_for_lang(lang: str) -> list[dict[str, str]]:
    """Return prompt templates for the given language code. Falls back to English for 'auto'."""
    if lang == "auto":
        return PROMPT_TEMPLATES["en"]
    return PROMPT_TEMPLATES.get(lang, PROMPT_TEMPLATES["en"])
