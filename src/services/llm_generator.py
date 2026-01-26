"""
LLM Response Generator
Generates legal responses with mandatory citations
Handles different document types: statutes (with § sections) and decisions (without)
Uses LangChain ChatOpenAI for automatic LangSmith tracing
"""

import os
import time
from typing import List, Dict, Generator
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
3. **Cite**: Support every claim with precise citations using the provided reference labels (e.g., [§ 4], [Lähde 1]).
4. **Translate**: If documents are in Swedish, Northern Sami, or English, translate relevant parts to Finnish for your answer.

CRITICAL RULES:
- **Strict Context Adherence**: Do not use external legal knowledge. If the answer is not in the context, state: "Annettujen asiakirjojen perusteella en löydä tietoa tästä."
- **Citation Mandatory**: Every factual statement must be immediately followed by its source citation.
- **Language**: Answer ALWAYS in Finnish, regardless of the document's original language.
- **Multilingual Sensitivity**: Pay attention to legal terms in Northern Sami (e.g., "rievdadeamis" for amendment) or Swedish ensuring accurate interpretation.

RESPONSE FORMAT:
1. **Direct Answer**: Start with a clear, direct answer to the question.
2. **Detailed Analysis**: Provide a structured explanation, breaking down complex points. Use bullet points for clarity.
3. **Citations**: Embed citations naturally within the text (e.g., "Lain mukaan... [§ 4]").
4. **Sources List**: Conclude with a list of used sources in the format:
   
   LÄHTEET:
   - [Document Title] (Dnro: [Number])
     URI: [Link]
     PDF: [Link if available]
"""


class LLMGenerator:
    """Generate responses using GPT-4o with citations and LangSmith tracing"""
    
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
        Generate response with citations
        
        Args:
            query: User question
            context_chunks: Retrieved chunks with metadata
            
        Returns:
            Response with citations
        """
        
        # Build context
        context = self._build_context(context_chunks)
        
        # Create messages using LangChain message types
        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=f"KYSYMYS: {query}\n\nKONTEKSTI:\n{context}")
        ]
        
        # Generate response with automatic LangSmith tracing
        logger.info("[LLM API] Calling ChatOpenAI (LangSmith traced)...")
        api_start = time.time()
        
        response = self.llm.invoke(messages)
        
        api_elapsed = time.time() - api_start
        logger.info(f"[LLM API] Completed in {api_elapsed:.2f}s")
        
        return response.content
    
    def stream_response(
        self, 
        query: str, 
        context_chunks: List[Dict]
    ):
        """
        Stream response with citations (for Streamlit)
        
        Args:
            query: User question
            context_chunks: Retrieved chunks with metadata
            
        Yields:
            Response chunks as they're generated
        """
        # Build context
        context = self._build_context(context_chunks)
        
        # Create messages using LangChain message types
        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=f"KYSYMYS: {query}\n\nKONTEKSTI:\n{context}")
        ]
        
        # Stream response with automatic LangSmith tracing
        for chunk in self.llm.stream(messages):
            if chunk.content:
                yield chunk.content
    
    def _build_context(self, chunks: List[Dict]) -> str:
        """
        Build context string from chunks with intelligent citation labels.
        Supports both Statutes (legacy format) and Case Law (new unified format).
        """
        context_parts = []
        source_counter = 1  # Counter for documents without section numbers
        
        for i, chunk in enumerate(chunks, 1):
            # 1. Normalize Content
            text = chunk.get('text') or chunk.get('chunk_text') or chunk.get('content') or ''
            
            # 2. Extract Metadata based on Source Type
            source = chunk.get('source', 'unknown')
            metadata = chunk.get('metadata', {})
            
            if source == 'case_law':
                # Case Law Format
                case_id = metadata.get('case_id', 'Unknown Case')
                court = metadata.get('court', '').upper()
                year = metadata.get('year')
                section_type = metadata.get('type', 'Section')
                
                title = f"{court} {case_id} ({year})"
                uri = metadata.get('url', f"https://finlex.fi/fi/oikeuskaytanto/{court.lower()}/ennakkopaatokset/{year}/{case_id.split(':')[-1]}")
                doc_num = metadata.get('case_number')
                
                # Use section type as the "section number" for labeling
                section_number = section_type.capitalize()
                
            else:
                # Statute / Legacy Format
                title = chunk.get('document_title') or metadata.get('title') or 'Unknown Document'
                uri = chunk.get('document_uri') or metadata.get('uri') or ''
                doc_num = chunk.get('document_number') or metadata.get('case_number')
                section_number = chunk.get('section_number') or metadata.get('section')

            # 3. Build Citation Label
            ref_label = self._get_reference_label(section_number, source_counter)
            if not section_number or (not str(section_number).startswith('§') and source != 'case_law'):
                source_counter += 1
            
            # 4. formatting
            # Get PDF URL from various possible locations
            pdf_url = self._extract_pdf_url(chunk)
            
            # Build source info
            source_info = f"Lähde: {title}"
            if doc_num:
                source_info += f" (Dnro: {doc_num})"
            
            # Build the context entry
            context_str = f"{ref_label} {text}\n{source_info}\nURI: {uri}"
            if pdf_url:
                context_str += f"\nPDF: {pdf_url}"
            
            context_parts.append(f"{context_str}\n")
        
        return "\n".join(context_parts)
    
    def _get_reference_label(self, section_number: str, source_counter: int) -> str:
        """
        Generate appropriate reference label based on document type.
        
        Args:
            section_number: Real section number from chunk (e.g., "§ 4", "Liite: X", or None)
            source_counter: Counter for non-section sources
            
        Returns:
            Reference label like [§ 4], [Liite: X], or [Lähde 1]
        """
        if not section_number:
            # No section number - use generic source reference
            return f"[Lähde {source_counter}]"
        
        # Check if it's a real § section (from statutes)
        if section_number.startswith('§'):
            return f"[{section_number}]"
        
        # Check if it's an attachment
        if section_number.startswith('Liite:'):
            return f"[{section_number}]"
        
        # Check if it's a preamble or other named section
        if section_number in ('Preamble', 'Johdanto'):
            return f"[{section_number}]"
        
        # For any other case (like section parts), use the section number
        if '(part' in section_number:
            # e.g., "§ 4 (part 1)" -> "[§ 4 (part 1)]"
            return f"[{section_number}]"
        
        # Default: use generic source reference
        return f"[Lähde {source_counter}]"
    
    def _extract_pdf_url(self, chunk: Dict) -> str:
        """
        Extract PDF URL from chunk metadata.
        
        Checks multiple possible locations for PDF URLs.
        
        Args:
            chunk: Chunk dictionary with metadata
            
        Returns:
            PDF URL string or empty string if not found
        """
        # Direct pdf_url field
        pdf_url = chunk.get('pdf_url')
        if pdf_url:
            return pdf_url
        
        # Check in metadata dict
        metadata = chunk.get('metadata', {})
        if isinstance(metadata, dict):
            pdf_url = metadata.get('pdf_url')
            if pdf_url:
                return pdf_url
            
            # Check pdf_files list
            pdf_files = metadata.get('pdf_files')
            if pdf_files and isinstance(pdf_files, list) and len(pdf_files) > 0:
                first_pdf = pdf_files[0]
                if isinstance(first_pdf, dict):
                    return first_pdf.get('pdf_url', '')
        
        return ""
