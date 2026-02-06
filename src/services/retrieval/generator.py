"""
LLM Response Generator
Generates legal responses with mandatory citations
Handles different document types: statutes (with § sections) and decisions (without)
Uses LangChain ChatOpenAI for automatic LangSmith tracing
"""

import os
import time
from typing import List, Dict, AsyncIterator
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from dotenv import load_dotenv
from src.config.logging_config import setup_logger

load_dotenv()
logger = setup_logger(__name__)


SYSTEM_PROMPT = """You are a highly capable AI legal assistant specialized in Finnish law. Your task is to provide accurate, well-reasoned answers based ONLY on the provided legal context.

CORE RESPONSIBILITIES:
1. **Analyze**: Carefully review the provided legal documents (statutes, case law, regulations).
2. **Reason**: Apply logical reasoning to connect facts from the documents to the user's question.
3. **Cite**: Support every claim with precise citations using the provided reference labels.
   - For statutes: use section labels (e.g., [§ 4]).
   - For case law: use the Case ID (e.g., [KKO:2026:5]).
   - DO NOT hallucinate citations. Use ONLY the labels provided in the context.
4. **Translate**: If documents are in Swedish, Northern Sami, or English, translate relevant parts to Finnish for your answer.

CRITICAL RULES:
- **Strict Context Adherence**: Do not use external legal knowledge. If the answer is not in the context, state: "Annettujen asiakirjojen perusteella en löydä tietoa tästä."
- **Citation Mandatory**: Every factual statement must be immediately followed by its source citation.
- **Language**: Answer ALWAYS in Finnish, regardless of the document's original language.
- **URL SECURITY**: You must ONLY provide URLs that are explicitly provided in the "URI:" field for each chunk in the context. 
- **NO HALLUCINATION**: DO NOT attempt to create or guess URLs. If a URI is provided, copy it EXACTLY as it is written. If no URI is provided, omit the URI field from your sources list.
- **NEVER use "/en/"** in a Finlex URL unless the provided URI explicitly contains it.

RESPONSE FORMAT:
1. **Direct Answer**: Start with a clear, direct answer to the question.
2. **Detailed Analysis**: Provide a structured explanation, breaking down complex points. Use bullet points for clarity.
3. **Citations**: Embed citations naturally within the text (e.g., "Lain mukaan... [§ 4]").
4. **Sources List**: Conclude with a list of used sources in the format:
   
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
            api_key=os.getenv("OPENAI_API_KEY")
        )
        self.model = model
    
    def generate_response(
        self, 
        query: str, 
        context_chunks: List[Dict]
    ) -> str:
        """
        Generate response with citations (Synchronous)
        """
        # Build context
        context = self._build_context(context_chunks)
        
        # Create messages
        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=f"KYSYMYS: {query}\n\nKONTEKSTI:\n{context}")
        ]
        
        logger.info("Calling LLM...")
        api_start = time.time()
        response = self.llm.invoke(messages)
        api_elapsed = time.time() - api_start
        logger.info(f"LLM done in {api_elapsed:.1f}s")
        
        return response.content

    async def agenerate_response(
        self, 
        query: str, 
        context_chunks: List[Dict]
    ) -> str:
        """
        Generate response with citations (Asynchronous)
        """
        # Build context
        context = self._build_context(context_chunks)
        
        # Create messages
        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=f"KYSYMYS: {query}\n\nKONTEKSTI:\n{context}")
        ]
        
        logger.info("Calling LLM...")
        api_start = time.time()
        response = await self.llm.ainvoke(messages)
        api_elapsed = time.time() - api_start
        logger.info(f"LLM done in {api_elapsed:.1f}s")
        
        return response.content
    
    async def astream_response(
        self, 
        query: str, 
        context_chunks: List[Dict]
    ) -> AsyncIterator[str]:
        """
        Stream response with citations (Asynchronous)
        """
        context = self._build_context(context_chunks)
        
        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=f"KYSYMYS: {query}\n\nKONTEKSTI:\n{context}")
        ]
        
        async for chunk in self.llm.astream(messages):
            if chunk.content:
                yield chunk.content
    
    def _build_context(self, chunks: List[Dict]) -> str:
        """
        Build context string from chunks with intelligent citation labels.
        Supports both Statutes (legacy format) and Case Law (new unified format).
        """
        context_parts = []
        source_counter = 1
        
        for i, chunk in enumerate(chunks, 1):
            text = chunk.get('text') or chunk.get('chunk_text') or chunk.get('content') or ''
            metadata = chunk.get('metadata', {})
            
            case_id = metadata.get('case_id')
            section_number = chunk.get('section_number') or metadata.get('section')
            doc_title = chunk.get('document_title') or metadata.get('title') or metadata.get('document_title') or 'Unknown Document'
            doc_num = chunk.get('document_number') or metadata.get('case_number')
            
            if case_id:
                ref_label = f"[{case_id}]"
                court_name = metadata.get('court', '').upper()
                title = f"{court_name} {case_id} ({metadata.get('year')})"
            elif section_number and str(section_number).strip().startswith('§'):
                ref_label = f"[{section_number}]"
                title = doc_title
            else:
                if doc_title and len(doc_title) < 50:
                    ref_label = f"[{doc_title}]"
                else:
                     ref_label = f"[Lähde {source_counter}]"
                source_counter += 1
                title = doc_title

            uri = metadata.get('url') or metadata.get('document_uri') or chunk.get('document_uri')
            if not uri and case_id and metadata.get('year'):
                 court = metadata.get('court', '').lower()
                 if court in ("supreme_administrative_court", "kho"):
                     court_path = "korkein-hallinto-oikeus"
                 else:
                     court_path = "korkein-oikeus"
                 
                 # The Finlex URL for Finnish precedents uses /fi/
                 case_num = case_id.split(':')[-1]
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
    
    def _extract_pdf_url(self, chunk: Dict) -> str:
        pdf_url = chunk.get('pdf_url')
        if pdf_url:
            return pdf_url
        
        metadata = chunk.get('metadata', {})
        if isinstance(metadata, dict):
            pdf_url = metadata.get('pdf_url')
            if pdf_url:
                return pdf_url
            pdf_files = metadata.get('pdf_files')
            if pdf_files and isinstance(pdf_files, list) and len(pdf_files) > 0:
                first_pdf = pdf_files[0]
                if isinstance(first_pdf, dict):
                    return first_pdf.get('pdf_url', '')
        return ""
