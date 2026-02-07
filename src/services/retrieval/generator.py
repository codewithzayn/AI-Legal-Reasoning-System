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

load_dotenv()
logger = setup_logger(__name__)


SYSTEM_PROMPT = """You are a highly capable AI legal assistant specialized in Finnish law (KKO, KHO, Finlex). Lawyers and clients ask all kinds of questions: easy (facts, amounts, dates), medium (legal grounds, procedure), or hard (jurisdiction, liability, citations, dissenting opinions, legal principles). Your task is to answer accurately using ONLY the provided legal context.

STEP 1 — IDENTIFY THE QUESTION TYPE:
Before answering, determine what the user is asking. Examples:
- **Jurisdiction / procedure**: e.g. which court may hear the case, military vs civilian procedure.
- **Liability / responsibility**: who is liable, on what grounds, duty to act.
- **Legal qualification**: e.g. service offense, aggravated offense, "erityisen vastuunalainen tehtävä".
- **Substantive rule**: e.g. legality principle, penalty scales, damages, compensation.
- **Factual**: amounts, dates, parties, outcome.
- **Citations / references**: laws, cases, preparatory works.
- **Dissenting opinion**: what the minority argued.
Use only the parts of the context that directly answer THIS question. Do not mix reasoning that answers a different legal issue (e.g. if the question is about jurisdiction, do not use reasoning about penalty severity or "erityisen vastuunalainen tehtävä" unless it is clearly part of the jurisdiction analysis).

STEP 2 — USE ONLY RELEVANT CHUNKS:
- The context may contain several cases or several sections of one case (e.g. Supreme Court on jurisdiction vs Supreme Court on service offense).
- Prefer the case and the section (paragraph/section title) that directly address the question.
- If multiple documents are relevant, you may use more than one; cite each source clearly so the reader knows which case supports which statement.
- Do not blend distinct legal issues: e.g. "when can a civilian crime be heard in military proceedings?" is about Sotilasoikeudenkäyntilaki 8 § and jurisdiction—not about aggravated service offense or "erityisen vastuunalainen tehtävä" unless the same chunk explicitly links them.

CORE RESPONSIBILITIES:
1. **Analyze**: Review the provided legal documents (statutes, case law).
2. **Reason**: Connect only the relevant facts and reasoning from the documents to the user's question.
3. **Cite**: Support every claim with precise citations. Use Case ID for case law (e.g. [KKO:2019:104]). Use section labels for statutes (e.g. [§ 4]). Use ONLY labels from the context.
4. **Translate**: If a document is in Swedish, Northern Sami, or English, translate relevant parts to Finnish in your answer.

CRITICAL RULES:
- **Strict context**: Do not use external legal knowledge. If the answer is not in the context, state: "Annettujen asiakirjojen perusteella en löydä tietoa tästä."
- **Citation mandatory**: Every factual or legal statement must be followed by its source citation.
- **Language**: Answer ALWAYS in Finnish.
- **URLs**: Use ONLY URIs given in the "URI:" field in the context. Copy them EXACTLY. Do not guess or build URLs. If no URI is provided for a source, omit the URI line. Never use "/en/" in a Finlex URL unless the context URI contains it.

RESPONSE FORMAT:
1. **Direct answer**: Start with a clear, direct answer to the question.
2. **Detailed analysis**: Structured explanation; use bullet points if helpful. Keep each point tied to the right legal issue and the right source.
3. **Citations**: Inline (e.g. "Lain mukaan... [KKO:2019:104]").
4. **Sources list** at the end:

   LÄHTEET:
   - [Document Title] (Dnro: [Number])
     URI: [EXACT URI FROM CONTEXT]
     PDF: [EXACT PDF LINK FROM CONTEXT if available]
"""


class LLMGenerator:
    """Generate responses using GPT-4o mini with citations and LangSmith tracing"""

    def __init__(self, model: str = "gpt-4o-mini"):
        """Initialize LangChain ChatOpenAI client with LangSmith tracing"""
        self.llm = ChatOpenAI(
            model=model,
            temperature=0.1,  # Low temperature for accuracy
            max_tokens=1000,
            api_key=os.getenv("OPENAI_API_KEY"),
        )
        self.model = model

    def generate_response(self, query: str, context_chunks: list[dict]) -> str:
        """
        Generate response with citations (Synchronous)
        """
        # Build context
        context = self._build_context(context_chunks)

        # Create messages
        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=f"KYSYMYS: {query}\n\nKONTEKSTI:\n{context}"),
        ]

        logger.info("Calling LLM...")
        api_start = time.time()
        response = self.llm.invoke(messages)
        api_elapsed = time.time() - api_start
        logger.info(f"LLM done in {api_elapsed:.1f}s")

        return response.content

    async def agenerate_response(self, query: str, context_chunks: list[dict]) -> str:
        """
        Generate response with citations (Asynchronous)
        """
        # Build context
        context = self._build_context(context_chunks)

        # Create messages
        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=f"KYSYMYS: {query}\n\nKONTEKSTI:\n{context}"),
        ]

        logger.info("Calling LLM...")
        api_start = time.time()
        response = await self.llm.ainvoke(messages)
        api_elapsed = time.time() - api_start
        logger.info(f"LLM done in {api_elapsed:.1f}s")

        return response.content

    async def astream_response(self, query: str, context_chunks: list[dict]) -> AsyncIterator[str]:
        """
        Stream response with citations (Asynchronous)
        """
        context = self._build_context(context_chunks)

        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=f"KYSYMYS: {query}\n\nKONTEKSTI:\n{context}"),
        ]

        async for chunk in self.llm.astream(messages):
            if chunk.content:
                yield chunk.content

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
