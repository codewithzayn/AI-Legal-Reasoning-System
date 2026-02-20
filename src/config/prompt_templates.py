"""
Editable prompt templates for the chat UI.
Lawyers can click a template to use it as their question.
Edit this file to add or change suggested prompts.
"""

# Each template has: label (shown on button) and prompt (sent when clicked)
# Keys: "en", "fi", "sv" for language. Use same keys as translations.
PROMPT_TEMPLATES: dict[str, list[dict[str, str]]] = {
    "en": [
        # Year-aware examples first — teach users about year filtering proactively
        {"label": "Fraud cases 2018–2023", "prompt": "Find KKO cases about fraud (petos) from 2018 to 2023"},
        {"label": "Theft — all years", "prompt": "What is the penalty for theft (varkaus)? Search all years."},
        # Specific case
        {"label": "Summarize specific case", "prompt": "Summarize case KKO:2024:76"},
        # Topic searches
        {"label": "Insurance contracts", "prompt": "Tell me about insurance contracts (vakuutussopimus)"},
        {"label": "Administrative court decisions", "prompt": "Find KHO cases about administrative law"},
        {"label": "Damages and compensation", "prompt": "Find cases about damages (vahingonkorvaus) from 2015 to 2022"},
        {"label": "Civil court jurisdiction", "prompt": "Tell me about civil court jurisdiction"},
    ],
    "fi": [
        # Vuositietoiset esimerkit ensin — opettaa käyttäjälle vuosisuodatuksen
        {"label": "Petostapaukset 2018–2023", "prompt": "Etsi KKO-tapauksia petoksesta vuosilta 2018–2023"},
        {"label": "Varkaus — kaikki vuodet", "prompt": "Mikä on varkauden (varkaus) rangaistus? Hae kaikki vuodet."},
        # Tietty tapaus
        {"label": "Tiivistä tapaus", "prompt": "Tiivistä tapaus KKO:2024:76"},
        # Aihekohtaiset haut
        {"label": "Vakuutussopimukset", "prompt": "Kerro vakuutussopimuksista"},
        {"label": "Hallinto-oikeuden päätökset", "prompt": "Etsi KHO-tapauksia hallinto-oikeudesta"},
        {"label": "Vahingonkorvaus 2015–2022", "prompt": "Etsi tapauksia vahingonkorvauksesta vuosilta 2015–2022"},
        {"label": "Siviilioikeus", "prompt": "Kerro siviilioikeuksien toimivaltasta"},
    ],
    "sv": [
        # Årsmedvetna exempel först — lär användaren om årsfiltrering
        {"label": "Bedrägerimål 2018–2023", "prompt": "Hitta KKO-fall om bedrägeri (petos) från 2018 till 2023"},
        {"label": "Stöld — alla år", "prompt": "Vad är straffet för stöld (varkaus)? Sök alla år."},
        # Specifikt fall
        {"label": "Sammanfatta fall", "prompt": "Sammanfatta fall KKO:2024:76"},
        # Ämnessökningar
        {"label": "Försäkringsavtal", "prompt": "Berätta om försäkringsavtal"},
        {"label": "Förvaltningsdomstol", "prompt": "Hitta KHO-fall om förvaltningsrätt"},
        {"label": "Skadestånd 2015–2022", "prompt": "Hitta fall om skadestånd (vahingonkorvaus) från 2015 till 2022"},
        {"label": "Civila domstolar", "prompt": "Berätta om civila domstolars behörighet"},
    ],
}


def get_templates_for_lang(lang: str) -> list[dict[str, str]]:
    """Return prompt templates for the given language code. Falls back to English for 'auto'."""
    if lang == "auto":
        return PROMPT_TEMPLATES["en"]
    return PROMPT_TEMPLATES.get(lang, PROMPT_TEMPLATES["en"])
