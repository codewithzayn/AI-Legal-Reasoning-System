"""
Shared legal topic keywords (EN / FI / SV).

Single source of truth — imported by both nodes.py and query_context.py
to ensure consistent legal-topic detection across the agent pipeline.
"""

# Tuple of lowercase substrings that signal a legal topic in any of the
# three supported languages: English, Finnish, Swedish.
LEGAL_TOPIC_KEYWORDS: tuple[str, ...] = (
    # --- Court / authority names ------------------------------------------
    "kko",
    "kho",
    "finlex",
    "ennakkopäätös",
    "tuomioistuin",
    # --- Finnish core legal terms -----------------------------------------
    "laki",
    "§",
    "pykälä",
    "tuomio",
    "rangaistus",
    "rikos",
    "rikosoikeus",
    "sopimus",
    "oikeus",
    "syyte",
    "valitus",
    "hakemus",
    "korvaus",
    "vahingonkorvaus",
    "vastuu",
    "tapaus",
    "hallinto",
    "vero",
    "vakuutus",
    "työoikeus",
    "siviili",
    "maahanmuutto",
    "ympäristö",
    # --- Finnish legal subjects -------------------------------------------
    "petos",
    "varkaus",
    "kavallus",
    "seuraus",
    "edellyty",
    "milloin",
    "missä tapauksessa",
    # --- English legal terms ----------------------------------------------
    "fraud",
    "theft",
    "embezzlement",
    "consequences",
    "damages",
    "liability",
    "case",
    "contract",
    "penalty",
    "administrative",
    "tax",
    "employment",
    "civil",
    "criminal",
    "insurance",
    "immigration",
    "environment",
    # --- Swedish legal terms ----------------------------------------------
    "bedrägeri",
    "stöld",
    "skadestånd",
    "straff",
    "avtal",
    "mål",
    "fall",
    "förvaltning",
    "skatt",
    "arbetsrätt",
    "civile",
    "straffrätt",
    "försäkring",
    "invandring",
    "miljö",
)
