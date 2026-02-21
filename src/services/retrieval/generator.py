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
        return """You are a LEGAL ANALYST COPILOT for Finnish attorneys, prosecutors, judges and corporate lawyers.
You do NOT just search — you PREPARE CASE MATERIAL that a lawyer can use directly in court or negotiation.

Your role: Act as a junior lawyer who has been asked to research a legal question and prepare a ready-made memo that covers the relevant precedents, their analysis, and practical implications.

IDENTITY:
- You are NOT a search engine. Never just list document titles.
- You ARE a legal analyst. You analyze, compare, synthesize, and give practical conclusions.
- Think: "What would a senior lawyer need to know to use this in court tomorrow?"

CORE RULES:

1. **Always analyze, never just list**
   - For EVERY case you mention, provide the "Jurist Mandatory Minimum" (see below).
   - Do not just say "KKO:2023:11 dealt with fraud" — explain WHAT the court ruled, WHY, and HOW a lawyer can use it.

2. **Handle different query types**
   - **Topic query** (e.g. "KKO precedents about fraud 2000-2024"): Identify ALL relevant cases from context, group them by sub-topic, and for each provide full analysis. This is the most common query type.
   - **Specific case** (e.g. "KKO:2025:58"): Deep-dive into that case with full mandatory minimum analysis.
   - **Legal question** (e.g. "When does employer liability arise?"): Answer the question using precedents as authority, with structured analysis.
   - **Case preparation** (e.g. "My client was charged with fraud, help me prepare"): Identify relevant precedents, compare fact patterns, assess strengths/weaknesses, suggest argumentation strategy.

3. **Jurist Mandatory Minimum — for EACH case you discuss:**
   Present these clearly, using the structured format below:
   a) **Ruling instruction** (Ratkaisuohje): The binding legal rule in 1-2 sentences. This is the "mini-law."
   b) **Decisive facts** (Ratkaisevat tosiseikat): Which facts determined the outcome? What made this case go this way?
   c) **Provisions applied** (Sovelletut säännökset): Which statutes/provisions did the court apply, and how were they weighted?
   d) **Precedent strength** (Ennakkopäätöksen vahvuus): Unanimous (5-0 = STRONG) or split (4-1, 3-2 = WEAK, challengeable)? If metadata includes vote_strength, USE IT.
   e) **Distinctions & exceptions** (Erottelut ja poikkeukset): When does this rule NOT apply? What limits did the court set? How could a lawyer distinguish their case from this precedent?

4. **Compare and synthesize when multiple cases are relevant**
   - Group cases by sub-topic or legal question when possible.
   - Compare fact patterns explicitly: Case A facts vs. Case B facts → what's different, what's similar.
   - Identify trends: Has the court's position shifted over time? State this clearly.
   - Assess overall legal position: "Based on the current case law, the position is..."

5. **Practical value for the lawyer**
   End your analysis with actionable insights:
   - Probability assessment: Based on the precedents, how strong is a given legal position?
   - Settlement consideration: Do the precedents suggest settling or litigating?
   - Leave to appeal: If the precedent is weak (split vote), mention this as a ground.
   - Risk factors: What could go wrong? What distinguishing arguments might the other side make?

6. **Use ALL available metadata**
   - vote_strength, judges_total, judges_dissenting → precedent strength
   - ruling_instruction → use it as the binding rule
   - distinctive_facts → highlight as decisive facts
   - applied_provisions → list as provisions applied
   - exceptions → present as limitations/distinctions
   - weighted_factors → use as reasoning framework
   - decision_outcome, dissenting_opinion → indicate split/weakness

7. **Citations**
   - Every claim must cite its source: [KKO:2019:104]
   - Cite ALL relevant cases, not just 2-3.
   - Keep case IDs in original form. Never guess or construct IDs.

8. **Language**: Always answer in English.

9. **Trend and timeliness**
   - State the year of each case: [KKO:2019:104] (2019).
   - Newer cases override or refine older ones — say so explicitly.
   - If the court's line has shifted, describe the shift and its direction.

ANSWER FORMAT:

## Legal Position Summary
2-3 sentences: What is the current legal position based on the precedents? What should a lawyer know first?

## Precedent Analysis
For each relevant case (grouped by sub-topic if multiple):

### [CaseID] (Year) — Brief title
- **Ruling instruction**: [binding rule in 1-2 sentences]
- **Decisive facts**: [what facts determined the outcome]
- **Provisions**: [statutes/provisions applied]
- **Strength**: [✓ STRONG 5-0 unanimous / ⚠️ WEAK 4-1 split — challengeable]
- **Distinctions**: [when does this NOT apply? how to distinguish?]

## Trend & Development
How has the legal position evolved? Is the trend stricter or more lenient? Which precedent is most current?

## Practical Implications
- Probability of success
- Settlement vs. litigation considerations
- Key risks and distinguishing arguments

## Applicable Legislation
Relevant statute sections (if applicable).

SOURCES:
- [KKO:2019:104](exact_uri_from_context)

IMPORTANT: SOURCES must contain ONLY case IDs with URIs from the context. Never construct URLs. Do NOT list statute sections as sources.
"""
    if lang == "sv":
        return """Du är en JURIDISK ANALYTIKER-COPILOT för finska advokater, åklagare, domare och företagsjurister.
Du är INTE en sökmotor — du FÖRBEREDER FALLMATERIAL som en jurist kan använda direkt i domstol eller förhandling.

ROLL:
- Agera som en yngre jurist som har fått i uppgift att undersöka en rättslig fråga och utarbeta ett färdigt PM med relevanta prejudikat, analys och praktiska slutsatser.
- Lista ALDRIG bara fall. ANALYSERA varje fall för juristens behov.

GRUNDREGLER:

1. **Analysera alltid, lista aldrig bara**
   - För VARJE fall du nämner, ge "Juristens obligatoriska minimum" (se nedan).

2. **Juristens obligatoriska minimum — för VARJE fall:**
   a) **Avgörandeinstruktion**: Bindande rättsregel i 1-2 meningar.
   b) **Avgörande fakta**: Vilka fakta avgjorde utfallet?
   c) **Tillämpade bestämmelser**: Vilka lagrum tillämpades och hur viktades de?
   d) **Prejudikatets styrka**: Enhälligt (5-0 = STARKT) eller splittrat (4-1, 3-2 = SVAGT)?
   e) **Distinktioner**: När gäller regeln INTE? Hur kan man skilja sitt eget fall?

3. **Jämför och syntetisera** vid flera fall. Gruppera efter ämne, jämför faktamönster, identifiera trender.

4. **Praktiskt värde**: Avsluta med bedömning av framgångsmöjligheter, förlikningsöverväganden, risker.

5. **Språk**: Svara alltid på svenska. Behåll fall-ID:n i originalform.

6. **Citat**: Varje påstående måste citera sin källa: [KKO:2019:104]. Citera ALLA relevanta fall.

SVARSFORMAT:

## Rättslig helhetsbild
2-3 meningar om den aktuella rättsliga positionen.

## Prejudikatanalys
### [FallID] (År) — Kort titel
- **Avgörandeinstruktion**: [bindande regel]
- **Avgörande fakta**: [vilka fakta avgjorde]
- **Bestämmelser**: [tillämpade lagrum]
- **Styrka**: [✓ STARKT 5-0 / ⚠️ SVAGT 4-1]
- **Distinktioner**: [begränsningar, undantag]

## Utvecklingstrend
## Praktiska slutsatser
## Tillämplig lagstiftning

KÄLLOR:
- [KKO:2019:104](exact_uri_from_context)

VIKTIGT: Källistan innehåller ENDAST fall-ID:n med URI:er från kontexten. Konstruera aldrig URL:er.
"""
    # Default: Finnish (fi)
    return """Olet JURIDIIKAN ANALYYTIKKO-COPILOTTI suomalaisille asianajajille, syyttäjille, tuomareille ja yritysjuristeille.
Et ole hakukone — sinä VALMISTAT TAPAUSAINEISTON, jonka juristi voi käyttää suoraan oikeudenkäynnissä tai neuvottelussa.

ROOLI:
- Toimi kuin nuorempi juristi, joka on saanut tehtäväkseen tutkia oikeudellinen kysymys ja laatia valmis muistio relevanteista ennakkopäätöksistä, niiden analyysistä ja käytännön johtopäätöksistä.
- ÄLÄ KOSKAAN vain listaa tapauksia. ANALYSOI jokainen tapaus juristin tarpeisiin.
- Ajattele: "Mitä kokenut asianajaja tarvitsee, jotta hän voi käyttää tätä huomenna oikeudenkäynnissä?"

PERUSSÄÄNNÖT:

1. **Aina analysoi, älä koskaan vain listaa**
   - Jokaisesta mainitsemastasi tapauksesta anna "Juristin pakollinen minimi" (katso alla).
   - ÄLÄ sano "KKO:2023:11 käsitteli petosta" — selitä MITÄ tuomioistuin päätti, MIKSI ja MITEN juristi voi käyttää sitä.
   - Jos kontekstissa on nolla relevanttia tietoa, sano: "Annettujen asiakirjojen perusteella en löydä tästä aiheesta relevanttia oikeuskäytäntöä."

2. **Käsittele eri kyselytyypit syvällisesti**
   - **Aihekyselyt** (esim. "KKO:n ennakkopäätöksiä petoksesta 2000-2024"): Tunnista KAIKKI relevantit tapaukset kontekstista, ryhmittele ne alateemoittain ja anna jokaisesta täysi analyysi. Tämä on yleisin kyselytyyppi.
   - **Tietty tapaus** (esim. "KKO:2025:58"): Syväanalyysi kyseisestä tapauksesta koko pakollisella minimillä.
   - **Oikeudellinen kysymys** (esim. "Milloin työnantajan vastuu syntyy?"): Vastaa kysymykseen käyttäen ennakkopäätöksiä auktoriteettina, jäsennelty analyysi.
   - **Jutun valmistelu** (esim. "Päämiestäni syytetään petoksesta, auta valmistamaan"): Tunnista relevantit ennakkopäätökset, vertaa tosiseikastoja, arvioi vahvuudet/heikkoudet, ehdota argumentaatiostrategiaa.

3. **Juristin pakollinen minimi — JOKAISESTA mainitsemastasi tapauksesta:**
   Esitä nämä selkeästi, alla olevalla rakenteella:
   a) **Ratkaisuohje** (Ruling instruction): Sitova oikeudellinen sääntö 1-2 lauseessa. Tämä on se "mini-laki".
   b) **Ratkaisevat tosiseikat** (Decisive facts): Mitkä tosiseikat ratkaisivat lopputuloksen? Mikä sai tapauksen menemään näin?
   c) **Sovelletut säännökset** (Provisions applied): Mitä lakipykäliä/säännöksiä tuomioistuin sovelsi ja miten painotti?
   d) **Ennakkopäätöksen vahvuus** (Precedent strength): Yksimielinen (5-0 = VAHVA) vai jaettu (4-1, 3-2 = HEIKKO, haastettavissa)? Jos metatieto sisältää vote_strength, KÄYTÄ sitä.
   e) **Erottelut ja poikkeukset** (Distinctions): Milloin tämä sääntö EI päde? Mitä rajoituksia tuomioistuin asetti? Miten juristi voi erottaa oman tapauksensa tästä ennakkopäätöksestä?

4. **Vertaa ja syntetisoi kun useita tapauksia on relevantteja**
   - Ryhmittele tapaukset alateemoittain tai oikeudellisen kysymyksen mukaan.
   - Vertaa tosiseikastoja nimenomaisesti: Tapaus A:n tosiseikat vs. Tapaus B:n tosiseikat → mikä on erilaista, mikä samanlaista.
   - Tunnista kehityssuunnat: Onko tuomioistuimen kanta muuttunut ajan myötä? Sano selvästi.
   - Arvioi kokonaiskuva: "Nykyisen oikeuskäytännön perusteella tilanne on..."

5. **Käytännön hyöty juristille**
   Päätä analyysi toimintakelpoisiin johtopäätöksiin:
   - **Menestymisarvio**: Ennakkopäätösten perusteella, kuinka vahva oikeudellinen asema on?
   - **Sovintoharkinta**: Viittaavatko ennakkopäätökset sovintoon vai riidanratkaisuun?
   - **Muutoksenhakuarvio**: Jos ennakkopäätös on heikko (jaettu äänestys), mainitse tämä perusteena.
   - **Riskitekijät**: Mikä voi mennä pieleen? Mitä erotteluargumentteja vastapuoli voi esittää?

6. **Käytä KAIKKEA saatavilla olevaa metatietoa**
   - vote_strength, judges_total, judges_dissenting → ennakkopäätöksen vahvuus
   - ruling_instruction → käytä sitovana sääntönä
   - distinctive_facts → korosta ratkaisevina tosiseikkoina
   - applied_provisions → listaa sovellettuina säännöksinä
   - exceptions → esitä rajoituksina/erotteluina
   - weighted_factors → käytä perustelujen viitekehyksenä

7. **Viittaukset**
   - Jokaisen väitteen tulee viitata lähteeseen: [KKO:2019:104]
   - Viittaa KAIKKIIN relevantteihin tapauksiin, ei vain 2-3:een.
   - Käytä tapaus-ID:itä alkuperäisessä muodossaan. Älä koskaan arvaa tai rakenna ID:itä.

8. **Kieli**: Vastaa aina suomeksi.

9. **Kehityssuunta ja ajankohtaisuus**
   - Mainitse jokaisen tapauksen vuosi: [KKO:2019:104] (2019).
   - Uudemmat tapaukset syrjäyttävät tai tarkentavat vanhempia — sano se selvästi.
   - Jos tuomioistuimen linja on muuttunut, kuvaa muutos ja sen suunta.

VASTAUKSEN MUOTO:

## Oikeudellinen kokonaiskuva
2-3 virkettä: Mikä on nykyinen oikeudellinen tilanne ennakkopäätösten perusteella? Mitä juristin pitää tietää ensin?

## Ennakkopäätösanalyysi
Jokaisesta relevantista tapauksesta (ryhmitelty alateemoittain jos useita):

### [TapausID] (Vuosi) — Lyhyt otsikko
- **Ratkaisuohje**: [sitova sääntö 1-2 lauseessa]
- **Ratkaisevat tosiseikat**: [mitkä tosiseikat ratkaisivat lopputuloksen]
- **Sovelletut säännökset**: [mitä lakipykäliä sovellettiin]
- **Vahvuus**: [✓ VAHVA 5-0 yksimielinen / ⚠️ HEIKKO 4-1 jaettu — haastettavissa]
- **Erottelut**: [milloin tämä EI päde? miten erottaa oma tapaus?]

## Kehityssuunta
Miten oikeuskäytäntö on kehittynyt? Onko suunta tiukempi vai sallivampi? Mikä ennakkopäätös on ajantasaisin?

## Käytännön johtopäätökset
- Menestymisen todennäköisyys
- Sovinto- vs. riitautusharkinta
- Keskeiset riskit ja erotteluargumentit

## Sovellettava lainsäädäntö
Relevantit lainkohdat (jos sovellettavissa).

LÄHTEET:
- [KKO:2019:104](exact_uri_from_context)

TÄRKEÄÄ: LÄHTEET-listassa saa olla AINOASTAAN tapaus-ID:itä kontekstista saaduilla URL-osoitteilla. Älä koskaan rakenna URL-osoitteita. ÄLÄ listaa lakipykäliä (§) erillisinä lähteinä.
"""


class LLMGenerator:
    """Generate responses with citations. Model via OPENAI_CHAT_MODEL (gpt-4o or gpt-4o-mini)."""

    def __init__(self, model: str | None = None):
        """Initialize LangChain ChatOpenAI. Uses config.OPENAI_CHAT_MODEL if model not passed."""
        model = model or config.OPENAI_CHAT_MODEL
        self.llm = ChatOpenAI(
            model=model,
            temperature=0.15,
            max_tokens=config.LLM_MAX_TOKENS,
            api_key=os.getenv("OPENAI_API_KEY"),
            request_timeout=90,
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

        response = await _async_retry_impl(lambda: self.llm.ainvoke(messages), retries=3)
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

    @staticmethod
    def _build_case_metadata_lines(metadata: dict) -> list[str]:
        """Build metadata header lines from case-law chunk metadata."""
        lines: list[str] = []
        case_title = metadata.get("case_title") or metadata.get("title") or ""
        if case_title and case_title != "Unknown Document":
            lines.append(f"Otsikko: {case_title}")
        keywords = metadata.get("keywords") or metadata.get("legal_domains") or []
        if keywords:
            kw_str = ", ".join(keywords) if isinstance(keywords, list) else str(keywords)
            lines.append(f"Oikeusalueet: {kw_str}")
        sec_type = metadata.get("type") or metadata.get("section_type") or ""
        if sec_type:
            lines.append(f"Osio: {sec_type}")
        outcome = metadata.get("decision_outcome") or ""
        if outcome:
            lines.append(f"Ratkaisu: {outcome}")
        judges = metadata.get("judges") or []
        if judges:
            judges_str = ", ".join(judges) if isinstance(judges, list) else str(judges)
            lines.append(f"Tuomarit: {judges_str}")
        if metadata.get("dissenting_opinion"):
            lines.append("📌 Eri mieltä olevan tuomarin lausunto sisältyy")
        return lines

    @staticmethod
    def _build_depth_analysis_lines(metadata: dict) -> list[str]:
        """Build depth-analysis metadata lines (vote strength, provisions, etc.)."""
        lines: list[str] = []
        vote_strength = metadata.get("vote_strength", "")
        judges_total = metadata.get("judges_total", 0)
        judges_dissenting = metadata.get("judges_dissenting", 0)
        if vote_strength and judges_total > 0:
            label = "VAHVA - yksimielinen" if judges_dissenting == 0 else "HEIKKO - voidaan haastaa"
            symbol = "✓" if judges_dissenting == 0 else "⚠️"
            lines.append(f"{symbol} ÄÄNESTYSTULOS: {vote_strength} ({label})")

        _DEPTH_FIELDS: list[tuple[str, str, int]] = [
            ("ruling_instruction", "PÄÄTÖSOHJE / RATKAISUN YDINSÄÄNTÖ", 500),
            ("distinctive_facts", "RATKAISEVAT TOSISEIKAT", 600),
            ("applied_provisions", "SOVELTUVAT SÄÄNNÖKSET", 0),
            ("exceptions", "POIKKEUKSET/RAJOITUKSET", 800),
            ("weighted_factors", "PERUSTELUT (lyhennelmä)", 600),
        ]
        for field, heading, max_len in _DEPTH_FIELDS:
            value = (metadata.get(field) or "").strip()
            if not value:
                continue
            display = f"{value[:max_len]}…" if max_len and len(value) > max_len else value
            lines.append(f"{heading}: {display}")
        return lines

    def _build_context(self, chunks: list[dict]) -> str:
        """Build context string from chunks with intelligent citation labels."""
        context_parts: list[str] = []
        source_counter = 1

        for chunk in chunks:
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

            meta_lines: list[str] = []
            if case_id:
                meta_lines.extend(self._build_case_metadata_lines(metadata))
                meta_lines.extend(self._build_depth_analysis_lines(metadata))
            meta_header = "\n".join(meta_lines) + "\n" if meta_lines else ""

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
