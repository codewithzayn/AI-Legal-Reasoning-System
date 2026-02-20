"""
LLM Response Generator
Generates legal responses with mandatory citations
Handles different document types: statutes (with § sections) and decisions (without)
Uses LangChain ChatOpenAI for automatic LangSmith tracing
"""

import os
import time
from collections.abc import AsyncIterator

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from src.config.logging_config import setup_logger
from src.config.settings import config  # load_dotenv() runs here

logger = setup_logger(__name__)


def _build_system_prompt(response_language: str) -> str:
    """Build system prompt with response language (fi, en, sv)."""
    lang = response_language or "fi"
    if lang == "en":
        return """You are an AI legal assistant for Finnish and EU law (KKO, KHO, CJEU, ECHR, Finlex statutes).

Your task: Answer the user's input using ONLY the provided legal context.
The input can be a specific question, a legal topic/keyword, a case ID, a request to find cases, or anything related to Finnish law.

CORE RULES:

1. **Always use the provided context**
   - Base your answer exclusively on the provided documents.
   - If the context contains relevant cases or statutes, USE THEM — summarize, explain, and cite them.
   - Say "Based on the provided documents, I cannot find information on this topic." ONLY if the context truly has ZERO relevant information.

2. **Handle different query types**
   - **Specific question**: Give a direct legal answer with analysis.
   - **Topic/keyword**: List and summarize the most relevant cases from the context that deal with this topic. Explain what each case decided.
   - **Case ID** (e.g. KKO:2024:76): Summarize the case's key facts, reasoning, and judgment from the context.
   - **Find cases**: List matching cases with brief summaries.
   - **Jurisdiction/procedure**: Answer based on the relevant provisions.

3. **Focus on the asked case** (when applicable)
   - If the question mentions a specific case (e.g. KKO:2025:58), base your answer primarily on that case.
   - Cite other cases only if: (a) the question explicitly requests comparison, or (b) the focus case references them.

4. **Use case metadata**
   - Each case in the context includes metadata: title, keywords (legal domains), section type, court, year, and URL.
   - Use this metadata to identify which cases are relevant to the user's query.

5. **Mandatory citations — cite ALL relevant sources**
   - Every factual or legal claim must cite its source case.
   - Cite ALL cases from the provided context that are relevant to the question — do NOT limit yourself to 2–3.
   - Format: [CaseID] for case law (e.g. [KKO:2019:104], [C-311/18], [ECLI:EU:C:2024:123])
   - You may mention statute sections inline, but do NOT list statutes as separate sources.
   - Use only case IDs that appear in the provided context.

6. **Language**
   - Always answer in English.

7. **Legal concept translation**
   - When explaining Finnish legal concepts, use the equivalent English legal term (e.g., kavallus → embezzlement, petos → fraud), not literal word-for-word translation.
   - Consider legal context and jurisdiction when choosing the right equivalent.

8. **Original-language citations**
   - Keep ALL case IDs (KKO:2024:76, KHO:2023:T97), statute references (§ 26), and legal citations in their original form.
   - Never translate or transliterate citations. Always write [KKO:2019:104] as-is.

ANSWER FORMAT — use ## markdown headings for each section (sections are optional for short answers):

## Conclusion
1-2 sentences summarizing the key finding.

## Analysis
Explain the relevant law/reasoning, or list relevant cases with summaries for topic queries. Include inline citations throughout (e.g. "According to the law... [KKO:2019:104]").

## Applicable Legislation
List relevant statute sections mentioned in the analysis (optional, only if statutes are relevant).

**Sources list** at end — list ONLY retrieved case IDs (KKO/KHO), NOT statute sections:

SOURCES:
- [KKO:2019:104](exact_uri_from_context)
- [KKO:2026:9](exact_uri_from_context)

IMPORTANT: The SOURCES list must contain ONLY actual case IDs (e.g. KKO:xxxx:xx) with their URLs from the context. Do NOT list statute paragraphs (§) as separate sources. Use ONLY URIs provided in the context. Never construct or guess URLs.
"""
    if lang == "sv":
        return """Du är en AI-assistent för finsk och EU-juridik (KKO, KHO, CJEU, ECHR, Finlex).

Din uppgift: Svara på användarens fråga med ENDAST den angivna rättsliga kontexten.

GRUNDREGLER:

1. **Använd alltid den angivna kontexten**
   - Basera ditt svar på de angivna dokumenten.
   - Om kontexten innehåller relevanta fall eller lagar, ANVÄND dem — sammanfatta, förklara och citera dem.
   - Säg "Baserat på de angivna dokumenten kan jag inte hitta information om detta ämne." ENDAST om kontexten har NOLL relevant information.

2. **Hantera olika frågetyper**
   - **Specifik fråga**: Ge ett direkt rättsligt svar med analys.
   - **Ämne/nyckelord**: Lista och sammanfatta de mest relevanta fallen från kontexten. Förklara vad varje fall beslutade.
   - **Fall-ID** (t.ex. KKO:2024:76): Sammanfatta fallets huvudfakta, motivering och dom.
   - **Hitta fall**: Lista matchande fall med korta sammanfattningar.
   - **Jurisdiktion/procedur**: Svara utifrån de relevanta bestämmelserna.

3. **Fokusera på det angivna fallet** (om tillämpligt)
   - Om frågan nämner ett specifikt fall (t.ex. KKO:2025:58), basera ditt svar främst på det fallet.
   - Citera andra fall endast om: (a) frågan uttryckligen kräver jämförelse, eller (b) fokusfallet refererar till dem.

4. **Använd fallmetadata**
   - Varje fall i kontexten innehåller metadata: titel, nyckelord (rättsliga områden), sektionstyp, domstol, år och URL.
   - Använd denna metadata för att identifiera vilka fall som är relevanta för användarens fråga.

5. **Obligatoriska citat — citera ALLA relevanta källor**
   - Varje faktapåstående eller rättsligt påstående måste citera sin källa.
   - Citera ALLA fall från kontexten som är relevanta för frågan — begränsa dig INTE till 2–3.
   - Format: [CaseID] för rättsfall (t.ex. [KKO:2019:104], [C-311/18], [ECLI:EU:C:2024:123])
   - Du får nämna lagparagrafer i texten, men lista INTE lagparagrafer som separata källor.
   - Använd endast fall-ID:n som finns i den angivna kontexten.

6. **Språk**
   - Svara alltid på svenska.

7. **Rättslig begreppsöversättning**
   - När du förklarar finska rättsliga begrepp, använd motsvarande svenska rättsterm (t.ex. kavallus → förskingring, petos → bedrägeri), inte ordagrann översättning.
   - Ta hänsyn till rättslig kontext och jurisdiktion.

8. **Originalcitat**
   - Behåll ALLA fall-ID:n (KKO:2024:76, KHO:2023:T97), lagparagrafer (§ 26) och rättsliga citat i originalform.
   - Översätt eller translitterera aldrig citat. Skriv alltid [KKO:2019:104] oförändrat.

SVARSFORMAT — använd ## markdown-rubriker för varje avsnitt (avsnitt är valfria för korta svar):

## Slutsats
1-2 meningar som sammanfattar huvudfyndet.

## Analys
Förklara relevant lag eller motivering, eller lista relevanta fall med sammanfattningar. Inkludera citat i texten (t.ex. "Enligt lagen... [KKO:2019:104]").

## Tillämplig lagstiftning
Lista relevanta lagparagrafer som nämns i analysen (valfritt, bara om lagstiftning är relevant).

**Källista** i slutet — lista ENDAST hämtade fall-ID:n (KKO/KHO), INTE lagparagrafer:

KÄLLOR:
- [KKO:2019:104](exact_uri_from_context)
- [KKO:2026:9](exact_uri_from_context)

VIKTIGT: Källistan måste innehålla ENDAST faktiska fall-ID:n (t.ex. KKO:xxxx:xx) med sina URL:er från kontexten. Lista INTE lagparagrafer (§) som separata källor. Använd ENDAST URI:er från kontexten. Konstruera eller gissa aldrig URL:er.
"""
    # Default: Finnish (fi)
    return """You are an AI legal assistant for Finnish and EU law (KKO, KHO, CJEU, ECHR, Finlex statutes).

Your task: Answer the user's input using ONLY the provided legal context.
The input can be a specific question, a legal topic/keyword, a case ID, a request to find cases, or anything related to Finnish law.

CORE RULES:

1. **Always use the provided context**
   - Base your answer exclusively on the provided documents.
   - If the context contains relevant cases or statutes, USE THEM — summarize, explain, and cite them.
   - Say "Annettujen asiakirjojen perusteella en löydä tietoa tästä." ONLY if the context truly has ZERO relevant information.

2. **Handle different query types**
   - **Specific question** (e.g. "Milloin voidaan tuomita...?"): Give a direct legal answer with analysis.
   - **Topic/keyword** (e.g. "Seksuaalirikos", "vahingonkorvaus"): List and summarize the most relevant cases from the context that deal with this topic. Explain what each case decided.
   - **Case ID** (e.g. "KKO:2024:76"): Summarize the case's key facts, reasoning, and judgment from the context.
   - **Find cases** (e.g. "Etsi tapauksia koskien..."): List matching cases with brief summaries.
   - **Jurisdiction/procedure** (e.g. "Kuka käsittelee..."): Answer based on the relevant provisions.

3. **Focus on the asked case** (when applicable)
   - If the question mentions a specific case (e.g. KKO:2025:58), base your answer primarily on that case.
   - Cite other cases only if: (a) the question explicitly requests comparison, or (b) the focus case references them.

4. **Use case metadata**
   - Each case in the context includes metadata: title, keywords (legal domains), section type, court, year, and URL.
   - Use this metadata to identify which cases are relevant to the user's query.
   - The title often contains the legal topic (e.g. "Seksuaalirikos - Lapsen seksuaalinen hyväksikäyttö").

5. **Mandatory citations — cite ALL relevant sources**
   - Every factual or legal claim must cite its source case.
   - Cite ALL cases from the provided context that are relevant to the question — do NOT limit yourself to 2–3.
   - Format: [CaseID] for case law (e.g. [KKO:2019:104], [C-311/18], [ECLI:EU:C:2024:123])
   - You may mention statute sections inline (e.g. "OYL 6 luvun 26 §:n mukaan"), but do NOT list statutes as separate sources.
   - Use only case IDs that appear in the provided context.

6. **Language**
   - Always answer in Finnish.
   - Translate Swedish/Sami/English sources as needed.

7. **Original-language citations**
   - Keep ALL case IDs (KKO:2024:76, KHO:2023:T97), statute references (§ 26), and legal citations in their original form.
   - Never translate or transliterate citations. Always write [KKO:2019:104] as-is.

ANSWER FORMAT — use ## markdown headings for each section (sections are optional for short answers):

## Johtopäätös
1-2 virkettä, jotka tiivistävät pääasiallisen löydöksen.

## Analyysi
Selitä relevantti lainsäädäntö/perustelu tai listaa relevantit tapaukset yhteenvedoin. Sisällytä viittauksia läpi tekstin (esim. "Lain mukaan... [KKO:2019:104]").

## Sovellettava lainsäädäntö
Listaa analyysissä mainitut relevantit lainkohdat (valinnainen, vain jos lainsäädäntö on relevanttia).

**Lähdeluettelo** lopussa — listaa AINOASTAAN haetut tapaus-ID:t (KKO/KHO), EI lakipykäliä:

LÄHTEET:
- [KKO:2019:104](exact_uri_from_context)
- [KKO:2026:9](exact_uri_from_context)

IMPORTANT: The LÄHTEET list must contain ONLY actual case IDs (e.g. KKO:xxxx:xx) with their URLs from the context. Do NOT list statute paragraphs (§) as separate sources. Use ONLY URIs provided in the context. Never construct or guess URLs.
"""


class LLMGenerator:
    """Generate responses with citations. Model via OPENAI_CHAT_MODEL (gpt-4o or gpt-4o-mini)."""

    def __init__(self, model: str | None = None):
        """Initialize LangChain ChatOpenAI. Uses config.OPENAI_CHAT_MODEL if model not passed."""
        model = model or config.OPENAI_CHAT_MODEL
        self.llm = ChatOpenAI(
            model=model,
            temperature=0.1,  # Low temperature for accuracy
            max_tokens=config.LLM_MAX_TOKENS,  # Room for comprehensive answers and more citations
            api_key=os.getenv("OPENAI_API_KEY"),
            request_timeout=30,  # 30s cap; retries are expensive
        )
        self.model = model

    def generate_response(
        self,
        query: str,
        context_chunks: list[dict],
        focus_case_ids: list[str] | None = None,
        response_language: str = "fi",
    ) -> str:
        """
        Generate response with citations (Synchronous).
        If focus_case_ids is set (e.g. user asked about KKO:2025:58), answer is focused on that case.
        response_language: "fi", "en", or "sv" — controls output language.
        """
        context = self._build_context(context_chunks)
        user_content = self._build_user_content(query, context, focus_case_ids, response_language)
        system_prompt = _build_system_prompt(response_language)
        messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_content)]

        logger.info("Calling LLM...")
        api_start = time.time()
        response = self._invoke_with_retry_sync(messages)
        api_elapsed = time.time() - api_start
        logger.info("LLM done in %.1fs", api_elapsed)

        return response.content

    def _invoke_with_retry_sync(self, messages):
        from src.utils.retry import _sync_retry_impl

        return _sync_retry_impl(lambda: self.llm.invoke(messages))

    async def agenerate_response(
        self,
        query: str,
        context_chunks: list[dict],
        focus_case_ids: list[str] | None = None,
        response_language: str = "fi",
        conversation_history: list[dict] | None = None,
    ) -> str:
        """
        Generate response with citations (Asynchronous).
        If focus_case_ids is set, answer is focused on that/those case(s).
        conversation_history: optional recent chat messages for context.
        """
        from src.utils.query_context import get_recent_context_for_llm

        conv_context = get_recent_context_for_llm(conversation_history or [], max_turns=3) or ""
        context = self._build_context(context_chunks)
        user_content = self._build_user_content(
            query, context, focus_case_ids, response_language, conversation_context=conv_context
        )
        system_prompt = _build_system_prompt(response_language)
        messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_content)]

        logger.info("Calling LLM...")
        api_start = time.time()
        from src.utils.retry import _async_retry_impl

        response = await _async_retry_impl(lambda: self.llm.ainvoke(messages), retries=1)
        api_elapsed = time.time() - api_start
        logger.info("LLM done in %.1fs", api_elapsed)

        return response.content

    async def astream_response(
        self,
        query: str,
        context_chunks: list[dict],
        focus_case_ids: list[str] | None = None,
        response_language: str = "fi",
        conversation_history: list[dict] | None = None,
    ) -> AsyncIterator[str]:
        """Stream response with citations. If focus_case_ids set, answer focuses on that case."""
        from src.utils.query_context import get_recent_context_for_llm

        conv_context = get_recent_context_for_llm(conversation_history or [], max_turns=3) or ""
        context = self._build_context(context_chunks)
        user_content = self._build_user_content(
            query, context, focus_case_ids, response_language, conversation_context=conv_context
        )
        system_prompt = _build_system_prompt(response_language)
        messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_content)]

        async for chunk in self.llm.astream(messages):
            if chunk.content:
                yield chunk.content

    def _build_user_content(
        self,
        query: str,
        context: str,
        focus_case_ids: list[str] | None = None,
        response_language: str = "fi",
        conversation_context: str = "",
    ) -> str:
        """Build the user message; when focus_case_ids is set, add instruction to focus on that case."""
        labels = {
            "en": (
                "QUESTION",
                "CONTEXT",
                "NOTE: The question refers to case(s): {}. Base your answer primarily on this case. Cite others only if the question requires comparison or the focus case explicitly references them.",
            ),
            "sv": (
                "FRÅGA",
                "KONTEXT",
                "OBS: Frågan avser fall: {}. Basera ditt svar främst på detta fall. Citera andra endast om frågan kräver jämförelse eller fokusfallet uttryckligen refererar till dem.",
            ),
            "fi": (
                "KYSYMYS",
                "KONTEKSTI",
                "HUOM: Kysymys viittaa tapaukseen/tapauksiin: {}. Perustele vastauksesi ensisijaisesti tähän tapaukseen. Viittaa muihin tapauksiin vain, jos kysymys niin vaatii tai kyseinen tapaus niihin nimenomaisesti viittaa. Älä laimenta vastausta muilla tapauksilla.",
            ),
        }
        lang = response_language or "fi"
        q_label, c_label, focus_tpl = labels.get(lang, labels["fi"])
        prefix = f"{conversation_context}" if conversation_context else ""
        base = f"{prefix}{q_label}: {query}\n\n{c_label}:\n{context}"
        if focus_case_ids:
            cases_str = ", ".join(focus_case_ids)
            base += f"\n\n{focus_tpl.format(cases_str)}"
            # Case-specific: structure as bullet points, be comprehensive
            if lang == "en":
                base += "\n\nFORMAT FOR THIS CASE-SPECIFIC QUERY: Structure your answer with bullet points. Include: • Keywords / Legal domains • Case year • Key facts / Background • Legal issues • Reasoning • Resolution / Outcome • Sources. Be comprehensive—include all relevant details from the case."
            elif lang == "sv":
                base += "\n\nFORMAT FÖR DENNA FALLSPECIFIKA FRÅGA: Strukturera ditt svar med punkter. Inkludera: • Nyckelord / Rättsliga områden • År • Huvudfakta / Bakgrund • Rättsliga frågor • Motivering • Beslut / Resultat • Källor. Var uttömmande—inkludera alla relevanta detaljer från fallet."
            else:
                base += "\n\nTAPAU KOHTAINEN MUOTOILU: Muotoile vastauksesi luettelomerkein. Sisällytä: • Asiasanat / Oikeusalueet • Vuosi • Keskeiset tosiasiat / Tausta • Oikeudelliset kysymykset • Perustelut • Ratkaisu / Tulos • Lähteet. Ole kattava—sisällytä kaikki tapaukseen liittyvät oleelliset tiedot."
        if lang == "en":
            base += "\n\nIMPORTANT: The context is in Finnish. When explaining Finnish legal terms (e.g. kavallus, petos, varkaus, vahingonkorvaus), use their English equivalents (embezzlement, fraud, theft, damages) — do NOT leave Finnish terms untranslated in your answer."
        elif lang == "sv":
            base += "\n\nVIKTIGT: Kontexten är på finska. När du förklarar finska rättstermer (t.ex. kavallus, petos, varkaus, vahingonkorvaus), använd deras svenska motsvarigheter (förskingring, bedrägeri, stöld, skadestånd) — lämna INTE finska termer oöversatta i ditt svar."
        return base

    @staticmethod
    def _resolve_case_url(case_id: str, metadata: dict) -> str:
        """Build a fallback URL for a case when no explicit URL is stored."""
        court = metadata.get("court", "").lower()
        year = metadata.get("year")
        if court in ("cjeu", "general_court"):
            celex = metadata.get("celex_number", "")
            if celex:
                return f"https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:{celex}"
            eu_num = metadata.get("eu_case_number", case_id)
            return f"https://curia.europa.eu/juris/liste.jsf?num={eu_num}&language=en"
        if court == "echr":
            return f"https://hudoc.echr.coe.int/eng?i={case_id}"
        court_path = "korkein-hallinto-oikeus" if court in ("supreme_administrative_court", "kho") else "korkein-oikeus"
        case_num = case_id.split(":")[-1]
        return f"https://www.finlex.fi/fi/oikeuskaytanto/{court_path}/ennakkopaatokset/{year}/{year}{case_num.zfill(4)}"

    def _build_context(self, chunks: list[dict]) -> str:
        """
        Build context string from chunks with intelligent citation labels.
        Supports both Statutes (legacy format) and Case Law (new unified format).
        """
        context_parts = []
        source_counter = 1

        for _i, chunk in enumerate(chunks, 1):
            text = chunk.get("text") or chunk.get("chunk_text") or chunk.get("content") or ""
            metadata = chunk.get("metadata", {})

            case_id = metadata.get("case_id")
            section_number = chunk.get("section_number") or metadata.get("section")
            doc_title = (
                chunk.get("document_title")
                or metadata.get("title")
                or metadata.get("document_title")
                or "Unknown Document"
            )
            doc_num = chunk.get("document_number") or metadata.get("case_number")

            if case_id:
                ref_label = f"[{case_id}]"
                court_name = metadata.get("court", "").upper()
                title = f"{court_name} {case_id} ({metadata.get('year')})"
            elif section_number and str(section_number).strip().startswith("§"):
                ref_label = f"[{section_number}]"
                title = doc_title
            else:
                ref_label = f"[{doc_title}]" if doc_title and len(doc_title) < 50 else f"[Lähde {source_counter}]"
                source_counter += 1
                title = doc_title

            uri = metadata.get("url") or metadata.get("document_uri") or chunk.get("document_uri")
            if not uri and case_id and metadata.get("year"):
                uri = self._resolve_case_url(case_id, metadata)

            pdf_url = self._extract_pdf_url(chunk)
            source_info = f"Lähde: {title}"
            if doc_num:
                source_info += f" (Dnro: {doc_num})"

            # Build metadata header so LLM sees case title, keywords, section type, decision outcome
            meta_lines = []
            if case_id:
                case_title = metadata.get("case_title") or metadata.get("title") or ""
                if case_title and case_title != "Unknown Document":
                    meta_lines.append(f"Otsikko: {case_title}")
                keywords = metadata.get("keywords") or metadata.get("legal_domains") or []
                if keywords:
                    kw_str = ", ".join(keywords) if isinstance(keywords, list) else str(keywords)
                    meta_lines.append(f"Oikeusalueet: {kw_str}")
                sec_type = metadata.get("type") or metadata.get("section_type") or ""
                if sec_type:
                    meta_lines.append(f"Osio: {sec_type}")
                outcome = metadata.get("decision_outcome") or ""
                if outcome:
                    meta_lines.append(f"Ratkaisu: {outcome}")
            meta_header = "\n".join(meta_lines)
            if meta_header:
                meta_header = meta_header + "\n"

            context_str = f"{ref_label}\n{meta_header}{text}\n{source_info}\nURI: {uri or ''}"
            if pdf_url:
                context_str += f"\nPDF: {pdf_url}"

            context_parts.append(f"{context_str}\n")

        return "\n".join(context_parts)

    def _extract_pdf_url(self, chunk: dict) -> str:
        pdf_url = chunk.get("pdf_url")
        if pdf_url:
            return pdf_url

        metadata = chunk.get("metadata", {})
        if isinstance(metadata, dict):
            pdf_url = metadata.get("pdf_url")
            if pdf_url:
                return pdf_url
            pdf_files = metadata.get("pdf_files")
            if pdf_files and isinstance(pdf_files, list) and len(pdf_files) > 0:
                first_pdf = pdf_files[0]
                if isinstance(first_pdf, dict):
                    return first_pdf.get("pdf_url", "")
        return ""
