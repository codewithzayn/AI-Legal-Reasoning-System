"""
Editable prompt templates for the chat UI.
Lawyers can click a template to use it as their question.
Edit this file to add or change suggested prompts.
"""

# Each template has: label (shown on button) and prompt (sent when clicked)
# Keys: "en", "fi", "sv" for language. Use same keys as translations.
PROMPT_TEMPLATES: dict[str, list[dict[str, str]]] = {
    "en": [
        {"label": "Find cases about fraud", "prompt": "Find KKO cases about fraud (petos)"},
        {"label": "Insurance contracts", "prompt": "Tell me about insurance contracts (vakuutussopimus)"},
        {"label": "Penalty for theft", "prompt": "What is the penalty for theft (varkaus)?"},
        {"label": "Summarize specific case", "prompt": "Summarize case KKO:2024:76"},
        {"label": "Administrative court decisions", "prompt": "Find KHO cases about administrative law"},
        {"label": "Damages and compensation", "prompt": "Find cases about damages (vahingonkorvaus)"},
        {"label": "Civil court jurisdiction", "prompt": "Tell me about civil court jurisdiction"},
    ],
    "fi": [
        {"label": "Etsi petostapauksia", "prompt": "Etsi KKO-tapauksia petoksesta"},
        {"label": "Vakuutussopimukset", "prompt": "Kerro vakuutussopimuksista"},
        {"label": "Varkauden rangaistus", "prompt": "Mikä on varkauden (varkaus) rangaistus?"},
        {"label": "Tiivistä tapaus", "prompt": "Tiivistä tapaus KKO:2024:76"},
        {"label": "Hallinto-oikeuden päätökset", "prompt": "Etsi KHO-tapauksia hallinto-oikeudesta"},
        {"label": "Vahingonkorvaus", "prompt": "Etsi tapauksia vahingonkorvauksesta"},
        {"label": "Siviilioikeus", "prompt": "Kerro siviilioikeuksien toimivaltasta"},
    ],
    "sv": [
        {"label": "Hitta fall om bedrägeri", "prompt": "Hitta KKO-fall om bedrägeri (petos)"},
        {"label": "Försäkringsavtal", "prompt": "Berätta om försäkringsavtal"},
        {"label": "Straff för stöld", "prompt": "Vad är straffet för stöld (varkaus)?"},
        {"label": "Sammanfatta fall", "prompt": "Sammanfatta fall KKO:2024:76"},
        {"label": "Förvaltningsdomstol", "prompt": "Hitta KHO-fall om förvaltningsrätt"},
        {"label": "Skadestånd", "prompt": "Hitta fall om skadestånd (vahingonkorvaus)"},
        {"label": "Civila domstolar", "prompt": "Berätta om civila domstolars behörighet"},
    ],
}


def get_templates_for_lang(lang: str) -> list[dict[str, str]]:
    """Return prompt templates for the given language code. Falls back to English for 'auto'."""
    if lang == "auto":
        return PROMPT_TEMPLATES["en"]
    return PROMPT_TEMPLATES.get(lang, PROMPT_TEMPLATES["en"])
