"""
LLM Response Generator
Generates legal responses with mandatory citations
Handles different document types: statutes (with § sections) and decisions (without)
Uses LangChain ChatOpenAI for automatic LangSmith tracing
"""

import os
import time
from collections.abc import AsyncIterator

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from src.config.logging_config import setup_logger
from src.config.settings import config

load_dotenv()
logger = setup_logger(__name__)


SYSTEM_PROMPT = """You are an AI legal assistant for Finnish law (KKO, KHO, Finlex statutes).

Your task: Answer the user's question using ONLY the provided legal context.

CORE RULES:

1. **Strict context only**
   - Base your answer exclusively on the provided documents
   - If the answer isn't in the context, say: "Annettujen asiakirjojen perusteella en löydä tietoa tästä."
   - Never use external legal knowledge

2. **Focus on the asked case** (when applicable)
   - If the question mentions a specific case (e.g. KKO:2025:58), base your answer primarily on that case
   - Cite other cases only if: (a) the question explicitly requests comparison, or (b) the focus case references them

3. **Use only relevant parts**
   - The context may contain multiple cases or multiple sections of one case
   - Use only the parts that directly answer the user's specific question
   - Don't mix different legal issues (e.g. if asked about jurisdiction, don't discuss penalty severity unless directly relevant)

4. **Mandatory citations**
   - Every factual or legal claim must cite its source
   - Format: [CaseID] for case law (e.g. [KKO:2019:104])
   - Format: [§ X] for statutes (e.g. [§ 4 Osakeyhtiölaki])
   - Use only citation labels provided in the context

5. **"When" / "Conditions" questions**
   - For questions about when/under what conditions something applies, base your answer on provisions that STATE the conditions
   - Don't infer conditions from cases about exceptions or exclusions (unless they explicitly state the governing rule)

6. **Language**
   - Always answer in Finnish
   - Translate Swedish/Sami/English sources as needed

ANSWER FORMAT:

1. **Direct answer** (1-2 sentences)
2. **Analysis** (explain the relevant law/reasoning)
3. **Inline citations** throughout (e.g. "Lain mukaan... [KKO:2019:104]")
4. **Sources list** at end:

LÄHTEET:
- [KKO:2019:104](exact_uri_from_context)
- [§ 4 Osakeyhtiölaki](exact_uri_from_context)

Use ONLY URIs provided in the context. Never construct or guess URLs.
"""


class LLMGenerator:
    """Generate responses with citations. Model via OPENAI_CHAT_MODEL (gpt-4o or gpt-4o-mini)."""

    def __init__(self, model: str | None = None):
        """Initialize LangChain ChatOpenAI. Uses config.OPENAI_CHAT_MODEL if model not passed."""
        model = model or config.OPENAI_CHAT_MODEL
        self.llm = ChatOpenAI(
            model=model,
            temperature=0.1,  # Low temperature for accuracy
            max_tokens=1000,
            api_key=os.getenv("OPENAI_API_KEY"),
        )
        self.model = model

    def generate_response(self, query: str, context_chunks: list[dict], focus_case_ids: list[str] | None = None) -> str:
        """
        Generate response with citations (Synchronous).
        If focus_case_ids is set (e.g. user asked about KKO:2025:58), answer is focused on that case.
        """
        context = self._build_context(context_chunks)
        user_content = self._build_user_content(query, context, focus_case_ids)
        messages = [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=user_content)]

        logger.info("Calling LLM...")
        api_start = time.time()
        response = self.llm.invoke(messages)
        api_elapsed = time.time() - api_start
        logger.info(f"LLM done in {api_elapsed:.1f}s")

        return response.content

    async def agenerate_response(
        self, query: str, context_chunks: list[dict], focus_case_ids: list[str] | None = None
    ) -> str:
        """
        Generate response with citations (Asynchronous).
        If focus_case_ids is set, answer is focused on that/those case(s).
        """
        context = self._build_context(context_chunks)
        user_content = self._build_user_content(query, context, focus_case_ids)
        messages = [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=user_content)]

        logger.info("Calling LLM...")
        api_start = time.time()
        response = await self.llm.ainvoke(messages)
        api_elapsed = time.time() - api_start
        logger.info(f"LLM done in {api_elapsed:.1f}s")

        return response.content

    async def astream_response(
        self, query: str, context_chunks: list[dict], focus_case_ids: list[str] | None = None
    ) -> AsyncIterator[str]:
        """Stream response with citations. If focus_case_ids set, answer focuses on that case."""
        context = self._build_context(context_chunks)
        user_content = self._build_user_content(query, context, focus_case_ids)
        messages = [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=user_content)]

        async for chunk in self.llm.astream(messages):
            if chunk.content:
                yield chunk.content

    def _build_user_content(self, query: str, context: str, focus_case_ids: list[str] | None = None) -> str:
        """Build the user message; when focus_case_ids is set, add instruction to focus on that case."""
        base = f"KYSYMYS: {query}\n\nKONTEKSTI:\n{context}"
        if focus_case_ids:
            cases_str = ", ".join(focus_case_ids)
            base += f"\n\nHUOM: Kysymys viittaa tapaukseen/tapauksiin: {cases_str}. Perustele vastauksesi ensisijaisesti tähän tapaukseen. Viittaa muihin tapauksiin vain, jos kysymys niin vaatii tai kyseinen tapaus niihin nimenomaisesti viittaa. Älä laimenta vastausta muilla tapauksilla."
        return base

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
                court = metadata.get("court", "").lower()
                if court in ("supreme_administrative_court", "kho"):
                    court_path = "korkein-hallinto-oikeus"
                else:
                    court_path = "korkein-oikeus"

                # The Finlex URL for Finnish precedents uses /fi/
                case_num = case_id.split(":")[-1]
                uri = f"https://www.finlex.fi/fi/oikeuskaytanto/{court_path}/ennakkopaatokset/{metadata.get('year')}/{metadata.get('year')}{case_num.zfill(4)}"

            pdf_url = self._extract_pdf_url(chunk)
            source_info = f"Lähde: {title}"
            if doc_num:
                source_info += f" (Dnro: {doc_num})"

            context_str = f"{ref_label} {text}\n{source_info}\nURI: {uri or ''}"
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
