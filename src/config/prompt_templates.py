"""
Editable prompt templates for the chat UI.
Lawyers can click a template to use it as their question.
Edit this file to add or change suggested prompts.
"""

# Each template has: label (shown on button) and prompt (sent when clicked)
# Keys: "en", "fi", "sv" for language. Use same keys as translations.
PROMPT_TEMPLATES: dict[str, list[dict[str, str]]] = {
    "en": [
        {
            "label": "Fraud analysis 2015\u20132024",
            "prompt": "Analyze KKO precedents about fraud (petos) from 2015 to 2024. For each case: ruling instruction, decisive facts, provisions, vote strength, and distinctions.",
        },
        {
            "label": "Prepare dismissal case",
            "prompt": "My client was dismissed from employment. Analyze KKO precedents on grounds for dismissal (ty\u00f6sopimuksen irtisanominen). What are the decisive facts, trends, and risk assessment?",
        },
        {
            "label": "Deep analysis KKO:2024:76",
            "prompt": "Full legal analysis of KKO:2024:76: ruling instruction, decisive facts, provisions applied, precedent strength, distinctions, and how it compares to related cases.",
        },
        {
            "label": "Damages risk assessment",
            "prompt": "Analyze KKO precedents on damages (vahingonkorvaus) from 2018\u20132024. What is the trend? When does liability arise and what are the exceptions?",
        },
        {
            "label": "Contract breach strategy",
            "prompt": "My client is sued for breach of contract. Analyze relevant KKO precedents: what are the decisive factors, how strong are the precedents, and what distinguishing arguments can be made?",
        },
    ],
    "fi": [
        {
            "label": "Petosanalyysi 2015\u20132024",
            "prompt": "Analysoi KKO:n ennakkop\u00e4\u00e4t\u00f6kset petoksesta vuosilta 2015\u20132024. Jokaisesta tapauksesta: ratkaisuohje, ratkaisevat tosiseikat, sovelletut s\u00e4\u00e4nn\u00f6kset, \u00e4\u00e4nestystulos ja erottelut.",
        },
        {
            "label": "Irtisanomistapauksen valmistelu",
            "prompt": "P\u00e4\u00e4miest\u00e4ni on irtisanottu ty\u00f6suhteesta. Analysoi KKO:n ennakkop\u00e4\u00e4t\u00f6kset irtisanomisperusteista. Mitk\u00e4 ovat ratkaisevat tosiseikat, kehityssuunta ja riskiarvio?",
        },
        {
            "label": "Syv\u00e4analyysi KKO:2024:76",
            "prompt": "T\u00e4ysi oikeudellinen analyysi tapauksesta KKO:2024:76: ratkaisuohje, ratkaisevat tosiseikat, sovelletut s\u00e4\u00e4nn\u00f6kset, ennakkop\u00e4\u00e4t\u00f6ksen vahvuus, erottelut ja vertailu muihin tapauksiin.",
        },
        {
            "label": "Vahingonkorvauksen riskiarvio",
            "prompt": "Analysoi KKO:n ennakkop\u00e4\u00e4t\u00f6kset vahingonkorvauksesta vuosilta 2018\u20132024. Mik\u00e4 on kehityssuunta? Milloin vastuu syntyy ja mitk\u00e4 ovat poikkeukset?",
        },
        {
            "label": "Sopimusrikkomusstrategia",
            "prompt": "P\u00e4\u00e4miest\u00e4ni vastaan on nostettu kanne sopimusrikkomuksesta. Analysoi relevantit KKO:n ennakkop\u00e4\u00e4t\u00f6kset: ratkaisevat tekij\u00e4t, ennakkop\u00e4\u00e4t\u00f6sten vahvuus ja erotteluargumentit.",
        },
    ],
    "sv": [
        {
            "label": "Bedr\u00e4gerianalys 2015\u20132024",
            "prompt": "Analysera KKO-prejudikat om bedr\u00e4geri (petos) fr\u00e5n 2015 till 2024. F\u00f6r varje fall: avg\u00f6randeinstruktion, avg\u00f6rande fakta, best\u00e4mmelser, r\u00f6ststyrka och distinktioner.",
        },
        {
            "label": "F\u00f6rbered upps\u00e4gningsfall",
            "prompt": "Min klient har blivit upps\u00e4gd. Analysera KKO-prejudikat om upps\u00e4gningsgrunder. Avg\u00f6rande fakta, trender och riskbed\u00f6mning.",
        },
        {
            "label": "Djupanalys KKO:2024:76",
            "prompt": "Full r\u00e4ttslig analys av KKO:2024:76: avg\u00f6randeinstruktion, avg\u00f6rande fakta, till\u00e4mpade best\u00e4mmelser, prejudikatets styrka, distinktioner.",
        },
        {
            "label": "Skadest\u00e5ndsriskbed\u00f6mning",
            "prompt": "Analysera KKO-prejudikat om skadest\u00e5nd fr\u00e5n 2018\u20132024. Trend? N\u00e4r uppst\u00e5r ansvar och vilka undantag finns?",
        },
        {
            "label": "Avtalsbrottsstrategi",
            "prompt": "Min klient st\u00e4ms f\u00f6r avtalsbrott. Analysera relevanta KKO-prejudikat: avg\u00f6rande faktorer, prejudikatets styrka och distinktionsargument.",
        },
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
            "category": "Case Preparation",
            "icon": "\U0001f4cb",
            "templates": [
                {
                    "label": "Prepare fraud defense",
                    "description": "Full case analysis: precedents, ruling instructions, risks",
                    "prompt": "My client is charged with fraud. Analyze KKO precedents on fraud (petos) from 2015\u20132024: ruling instruction, decisive facts, vote strength, exceptions. What is the risk level?",
                },
                {
                    "label": "Employment dispute analysis",
                    "description": "Dismissal grounds, trends, and settlement assessment",
                    "prompt": "My client was dismissed. Analyze KKO precedents on dismissal grounds (irtisanomisperuste) 2018\u20132024. Decisive facts, precedent strength, trends, and settlement recommendation.",
                },
            ],
        },
        {
            "category": "Precedent Analysis",
            "icon": "\U0001f50d",
            "templates": [
                {
                    "label": "Deep-dive a case",
                    "description": "Full mandatory minimum: rule, facts, strength, distinctions",
                    "prompt": "Full legal analysis of KKO:2024:76: ruling instruction, decisive facts, provisions, vote strength, how to distinguish my case from this precedent.",
                },
                {
                    "label": "Compare precedents",
                    "description": "Compare two areas to find decisive differences",
                    "prompt": "Compare KKO precedents on theft vs. embezzlement: what are the decisive distinguishing factors?",
                },
            ],
        },
        {
            "category": "Risk & Strategy",
            "icon": "\U0001f3af",
            "templates": [
                {
                    "label": "Win probability assessment",
                    "description": "Evaluate chances based on precedent strength and trends",
                    "prompt": "Based on KKO precedents on damages (vahingonkorvaus) 2018\u20132024: what is the probability of success? Which precedents are strong (unanimous) vs. weak (split vote)?",
                },
                {
                    "label": "Counter-arguments & distinctions",
                    "description": "Find weaknesses in opposing precedents",
                    "prompt": "The opposing party cites strict liability in a product damage case. What counter-arguments and distinguishing precedents can I use?",
                },
            ],
        },
    ],
    "fi": [
        {
            "category": "Jutun valmistelu",
            "icon": "\U0001f4cb",
            "templates": [
                {
                    "label": "Petossyytteen puolustus",
                    "description": "T\u00e4ysi tapausanalyysi: ennakkop\u00e4\u00e4t\u00f6kset, ratkaisuohjeet, riskit",
                    "prompt": "P\u00e4\u00e4miest\u00e4ni syytet\u00e4\u00e4n petoksesta. Analysoi KKO:n ennakkop\u00e4\u00e4t\u00f6kset petoksesta 2015\u20132024: ratkaisuohje, ratkaisevat tosiseikat, \u00e4\u00e4nestystulos, poikkeukset. Mik\u00e4 on riskitaso?",
                },
                {
                    "label": "Ty\u00f6riidan analyysi",
                    "description": "Irtisanomisperusteet, kehityssuunta ja sovintoarvio",
                    "prompt": "P\u00e4\u00e4mieheni on irtisanottu. Analysoi KKO:n ennakkop\u00e4\u00e4t\u00f6kset irtisanomisperusteista 2018\u20132024. Ratkaisevat tosiseikat, ennakkop\u00e4\u00e4t\u00f6sten vahvuus, kehityssuunta ja sovintosuositus.",
                },
            ],
        },
        {
            "category": "Ennakkop\u00e4\u00e4t\u00f6sanalyysi",
            "icon": "\U0001f50d",
            "templates": [
                {
                    "label": "Syv\u00e4analyysi tapauksesta",
                    "description": "Pakollinen minimi: s\u00e4\u00e4nt\u00f6, tosiseikat, vahvuus, erottelut",
                    "prompt": "T\u00e4ysi oikeudellinen analyysi tapauksesta KKO:2024:76: ratkaisuohje, ratkaisevat tosiseikat, sovelletut s\u00e4\u00e4nn\u00f6kset, \u00e4\u00e4nestystulos, miten erotella oma tapaus.",
                },
                {
                    "label": "Vertaa ennakkop\u00e4\u00e4t\u00f6ksi\u00e4",
                    "description": "Vertaa kahta aluetta l\u00f6yt\u00e4\u00e4ksesi ratkaisevat erot",
                    "prompt": "Vertaa KKO:n ennakkop\u00e4\u00e4t\u00f6ksi\u00e4 varkaudesta ja kavalluksesta: mitk\u00e4 ovat ratkaisevat erottelutekij\u00e4t?",
                },
            ],
        },
        {
            "category": "Riski ja strategia",
            "icon": "\U0001f3af",
            "templates": [
                {
                    "label": "Menestymisarvio",
                    "description": "Arvioi mahdollisuudet ennakkop\u00e4\u00e4t\u00f6sten vahvuuden ja trendien perusteella",
                    "prompt": "KKO:n ennakkop\u00e4\u00e4t\u00f6sten perusteella vahingonkorvauksesta 2018\u20132024: menestymisen todenn\u00e4k\u00f6isyys? Mitk\u00e4 ennakkop\u00e4\u00e4t\u00f6kset ovat vahvoja (yksimielinen) vs. heikkoja (jaettu \u00e4\u00e4nestys)?",
                },
                {
                    "label": "Vasta-argumentit ja erottelut",
                    "description": "Etsi heikkouksia vastapuolen ennakkop\u00e4\u00e4t\u00f6ksist\u00e4",
                    "prompt": "Vastapuoli vetoaa ankaraan vastuuseen tuotevahinkoasiassa. Mit\u00e4 vasta-argumentteja ja erottelevia ennakkop\u00e4\u00e4t\u00f6ksi\u00e4 voin k\u00e4ytt\u00e4\u00e4?",
                },
            ],
        },
    ],
    "sv": [
        {
            "category": "Fallf\u00f6rberedelse",
            "icon": "\U0001f4cb",
            "templates": [
                {
                    "label": "Bedr\u00e4gerif\u00f6rsvar",
                    "description": "Full fallanalys: prejudikat, avg\u00f6randeinstruktioner, risker",
                    "prompt": "Min klient \u00e5talas f\u00f6r bedr\u00e4geri. Analysera KKO-prejudikat 2015\u20132024: avg\u00f6randeinstruktion, avg\u00f6rande fakta, r\u00f6ststyrka, undantag. Riskniv\u00e5?",
                },
                {
                    "label": "Arbetskonfliktanalys",
                    "description": "Upps\u00e4gningsgrunder, trender och f\u00f6rlikningsbed\u00f6mning",
                    "prompt": "Min klient har blivit upps\u00e4gd. Analysera KKO-prejudikat om upps\u00e4gningsgrunder 2018\u20132024: avg\u00f6rande fakta, styrka, trend, f\u00f6rlikningsrekommendation.",
                },
            ],
        },
        {
            "category": "Prejudikatanalys",
            "icon": "\U0001f50d",
            "templates": [
                {
                    "label": "Djupanalys av fall",
                    "description": "Obligatoriskt minimum: regel, fakta, styrka, distinktioner",
                    "prompt": "Full r\u00e4ttslig analys av KKO:2024:76: avg\u00f6randeinstruktion, avg\u00f6rande fakta, best\u00e4mmelser, r\u00f6ststyrka, distinktioner.",
                },
                {
                    "label": "J\u00e4mf\u00f6r prejudikat",
                    "description": "J\u00e4mf\u00f6r tv\u00e5 omr\u00e5den f\u00f6r att hitta avg\u00f6rande skillnader",
                    "prompt": "J\u00e4mf\u00f6r KKO-prejudikat om st\u00f6ld vs. f\u00f6rskingring: avg\u00f6rande distinktionsfaktorer?",
                },
            ],
        },
        {
            "category": "Risk och strategi",
            "icon": "\U0001f3af",
            "templates": [
                {
                    "label": "Framg\u00e5ngsbed\u00f6mning",
                    "description": "Utv\u00e4rdera chanser baserat p\u00e5 prejudikatets styrka och trender",
                    "prompt": "Baserat p\u00e5 KKO-prejudikat om skadest\u00e5nd 2018\u20132024: sannolikhet f\u00f6r framg\u00e5ng? Vilka prejudikat \u00e4r starka (enh\u00e4lliga) vs. svaga (splittrade)?",
                },
                {
                    "label": "Motargument och distinktioner",
                    "description": "Hitta svagheter i motpartens prejudikat",
                    "prompt": "Motparten h\u00e4nvisar till strikt ansvar i produktskadem\u00e5l. Vilka motargument och s\u00e4rskiljande prejudikat kan jag anv\u00e4nda?",
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
