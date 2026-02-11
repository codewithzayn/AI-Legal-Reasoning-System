TRANSLATIONS = {
    "en": {
        "page_title": "AI Legal Reasoning System",
        "header_title": "Finnish Legal Reasoning",
        "header_subtitle": "Ask about statutes, case law, and regulations in Finnish or English.",
        "ask_question": "Ask a question",
        "send": "Send",
        "input_hint": "Ask about Finnish law in Finnish or English.",
        "placeholder": "Ask me about Finnish legal documents.",
        "settings": "Settings",
        "language": "Language",
        "clear_chat": "Clear Chat History",
        "system": "System",
        "messages_count": "Messages: {count}",
        "spinner_searching": "Searching knowledge base...",
        "stream_analyzing": "Analyzing question...",
        "stream_searching": "Searching... (Found {count} results)",
        "stream_reformulating": "No results found. Refining search: '{query}'...",
        "stream_relevancy": "Relevancy: {score}/5. {reason}",
        "stream_relevancy_short": "Relevancy: {score}/5.",
        "stream_error": "Error: {error}",
        "stream_connection_error": "Connection error: {error}",
    },
    "fi": {
        "page_title": "Tekoälypohjainen oikeudellinen päättelyjärjestelmä",
        "header_title": "Suomalainen oikeudellinen päättely",
        "header_subtitle": "Kysy säädöksistä, oikeuskäytännöstä ja määräyksistä suomeksi tai englanniksi.",
        "ask_question": "Esitä kysymys",
        "send": "Lähetä",
        "input_hint": "Kysy Suomen lainsäädännöstä suomeksi tai englanniksi.",
        "placeholder": "Tervetuloa! Kysy minulta Suomen lainsäädännöstä.",
        "settings": "Asetukset",
        "language": "Kieli",
        "clear_chat": "Tyhjennä keskusteluhistoria",
        "system": "Järjestelmä",
        "messages_count": "Viestit: {count}",
        "spinner_searching": "Haetaan tietokannasta...",
        "stream_analyzing": "Analysoidaan kysymystä...",
        "stream_searching": "Etsitään tietoa... (Löydetty {count} tulosta)",
        "stream_reformulating": "Hakutuloksia ei löytynyt. Tarkennetaan hakua: '{query}'...",
        "stream_relevancy": "Relevanssi: {score}/5. {reason}",
        "stream_relevancy_short": "Relevanssi: {score}/5.",
        "stream_error": "Virhe: {error}",
        "stream_connection_error": "Virhe yhteydessä: {error}",
    },
}

LANGUAGE_OPTIONS = {"English": "en", "Suomi": "fi"}
DEFAULT_LANGUAGE = "en"


def t(key: str, lang: str = None, **kwargs) -> str:
    if lang is None:
        lang = DEFAULT_LANGUAGE
    text = TRANSLATIONS.get(lang, TRANSLATIONS[DEFAULT_LANGUAGE]).get(key, key)
    if kwargs:
        text = text.format(**kwargs)
    return text
