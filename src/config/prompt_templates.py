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


# ---------------------------------------------------------------------------
#  Structured Workflow Categories — categorized templates for welcome screen
# ---------------------------------------------------------------------------

WORKFLOW_CATEGORIES: dict[str, list[dict]] = {
    "en": [
        {
            "category": "Case Law",
            "icon": "\U0001f4dc",
            "templates": [
                {
                    "label": "Find precedents",
                    "description": "Search for landmark decisions on a topic",
                    "prompt": "Find precedent cases about fraud",
                },
                {
                    "label": "Summarize a case",
                    "description": "Get a structured summary of a specific case",
                    "prompt": "Summarize case KKO:2024:76",
                },
            ],
        },
        {
            "category": "Analysis",
            "icon": "\U0001f50d",
            "templates": [
                {
                    "label": "Analyze a case",
                    "description": "Deep analysis of facts, reasoning, and outcome",
                    "prompt": "Analyze the legal reasoning in KKO:2024:76",
                },
                {
                    "label": "Compare provisions",
                    "description": "Compare two legal provisions or case outcomes",
                    "prompt": "Compare provisions on theft and embezzlement",
                },
            ],
        },
        {
            "category": "Strategy",
            "icon": "\U0001f3af",
            "templates": [
                {
                    "label": "Risk assessment",
                    "description": "Evaluate legal risks based on case law",
                    "prompt": "What are the legal risks related to breach of contract based on recent case law?",
                },
                {
                    "label": "Counter-arguments",
                    "description": "Find opposing precedents and arguments",
                    "prompt": "What counter-arguments exist against strict liability in product damage cases?",
                },
            ],
        },
    ],
    "fi": [
        {
            "category": "Oikeusk\u00e4yt\u00e4nt\u00f6",
            "icon": "\U0001f4dc",
            "templates": [
                {
                    "label": "Etsi ennakkop\u00e4\u00e4t\u00f6ksi\u00e4",
                    "description": "Hae merkitt\u00e4vi\u00e4 p\u00e4\u00e4t\u00f6ksi\u00e4 aiheesta",
                    "prompt": "Etsi ennakkop\u00e4\u00e4t\u00f6ksi\u00e4 petoksesta",
                },
                {
                    "label": "Tiivist\u00e4 tapaus",
                    "description": "Saat j\u00e4sennellyn yhteenvedon tapauksesta",
                    "prompt": "Tiivist\u00e4 tapaus KKO:2024:76",
                },
            ],
        },
        {
            "category": "Analyysi",
            "icon": "\U0001f50d",
            "templates": [
                {
                    "label": "Analysoi tapaus",
                    "description": "Syvällinen analyysi tosiseikoista, perusteluista ja lopputuloksesta",
                    "prompt": "Analysoi oikeudellinen p\u00e4\u00e4ttely tapauksessa KKO:2024:76",
                },
                {
                    "label": "Vertaa s\u00e4\u00e4nn\u00f6ksi\u00e4",
                    "description": "Vertaa kahta lains\u00e4\u00e4nn\u00f6st\u00e4 tai tapausratkaisua",
                    "prompt": "Vertaa varkauden ja kavalluksen s\u00e4\u00e4nn\u00f6ksi\u00e4",
                },
            ],
        },
        {
            "category": "Strategia",
            "icon": "\U0001f3af",
            "templates": [
                {
                    "label": "Riskiarviointi",
                    "description": "Arvioi oikeudelliset riskit oikeusk\u00e4yt\u00e4nn\u00f6n perusteella",
                    "prompt": "Mitk\u00e4 ovat sopimusrikkomukseen liittyv\u00e4t oikeudelliset riskit viimeaikaisen oikeusk\u00e4yt\u00e4nn\u00f6n perusteella?",
                },
                {
                    "label": "Vasta-argumentit",
                    "description": "Etsi vastakkaisia ennakkop\u00e4\u00e4t\u00f6ksi\u00e4 ja argumentteja",
                    "prompt": "Mit\u00e4 vasta-argumentteja on ankaran vastuun soveltamista vastaan tuotevahinkoasioissa?",
                },
            ],
        },
    ],
    "sv": [
        {
            "category": "R\u00e4ttspraxis",
            "icon": "\U0001f4dc",
            "templates": [
                {
                    "label": "Hitta prejudikat",
                    "description": "S\u00f6k efter viktiga avg\u00f6randen om ett \u00e4mne",
                    "prompt": "Hitta prejudikat om bedr\u00e4geri",
                },
                {
                    "label": "Sammanfatta fall",
                    "description": "F\u00e5 en strukturerad sammanfattning av ett fall",
                    "prompt": "Sammanfatta fall KKO:2024:76",
                },
            ],
        },
        {
            "category": "Analys",
            "icon": "\U0001f50d",
            "templates": [
                {
                    "label": "Analysera fall",
                    "description": "Djupanalys av fakta, motivering och resultat",
                    "prompt": "Analysera det r\u00e4ttsliga resonemanget i KKO:2024:76",
                },
                {
                    "label": "J\u00e4mf\u00f6r best\u00e4mmelser",
                    "description": "J\u00e4mf\u00f6r tv\u00e5 best\u00e4mmelser eller fallresultat",
                    "prompt": "J\u00e4mf\u00f6r best\u00e4mmelser om st\u00f6ld och f\u00f6rskingring",
                },
            ],
        },
        {
            "category": "Strategi",
            "icon": "\U0001f3af",
            "templates": [
                {
                    "label": "Riskbed\u00f6mning",
                    "description": "Utv\u00e4rdera r\u00e4ttsliga risker baserat p\u00e5 r\u00e4ttspraxis",
                    "prompt": "Vilka \u00e4r de r\u00e4ttsliga riskerna vid avtalsbrott baserat p\u00e5 nyare r\u00e4ttspraxis?",
                },
                {
                    "label": "Motargument",
                    "description": "Hitta motsatta prejudikat och argument",
                    "prompt": "Vilka motargument finns mot strikt ansvar i produktskadem\u00e5l?",
                },
            ],
        },
    ],
}


def get_workflow_categories(lang: str) -> list[dict]:
    """Return workflow categories for the given language. Falls back to English for 'auto'."""
    if lang == "auto":
        return WORKFLOW_CATEGORIES["en"]
    return WORKFLOW_CATEGORIES.get(lang, WORKFLOW_CATEGORIES["en"])
