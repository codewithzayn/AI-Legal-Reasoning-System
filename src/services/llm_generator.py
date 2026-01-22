"""
LLM Response Generator
Generates legal responses with mandatory citations
Handles different document types: statutes (with § sections) and decisions (without)
"""

import os
import time
from typing import List, Dict, Generator
from openai import OpenAI
from dotenv import load_dotenv
from src.config.logging_config import setup_logger

load_dotenv()
logger = setup_logger(__name__)


SYSTEM_PROMPT = """You are a multilingual Finnish legal assistant. Answer questions based ONLY on the provided legal documents.

CRITICAL RULES:
1. Use ONLY the provided context to find facts.
2. ALWAYS cite sources using the reference labels provided in the context (e.g., [§ 4] for statutes, [Lähde 1] for decisions).
3. If information is not in context, say: "Annettujen asiakirjojen perusteella en löydä tietoa tästä"
4. **Translation is NOT external knowledge**: You are required to translate documents from Northern Sami (sme@), Swedish, or English into Finnish/English as needed to answer the question.
5. Quote exact text when possible.
6. **ALWAYS respond in Finnish language.**
7. **MULTILINGUAL REASONING**: You may receive documents in Northern Sami. For example, keywords like "rievdadeamis" (muuttamisesta / amending) and "ásahussii" (asetukseen / to decree) are critical.

CITATION FORMAT (IMPORTANT):
- Use the EXACT reference labels provided in the context (e.g., [§ 4], [Lähde 1], [Liite: X])
- **DO NOT invent or create your own reference numbers**
- If a source has a PDF link, include it in the LÄHTEET section

RESPONSE STRUCTURE:
1. Direct answer to question (in Finnish)
2. Supporting details with citations using the provided reference labels
3. Sources at end in format:
   
LÄHTEET:
- Document title (Dnro if available)
  URI: https://...
  PDF: https://... (vain jos PDF on saatavilla / only if PDF is available)
"""


class LLMGenerator:
    """Generate responses using GPT-4o with citations"""
    
    def __init__(self, model: str = "gpt-4o-mini"):
        """Initialize OpenAI client"""
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
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
        
        # Create messages
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"KYSYMYS: {query}\n\nKONTEKSTI:\n{context}"}
        ]
        
        # Generate response
        logger.info("[LLM API] Calling OpenAI...")
        api_start = time.time()
        
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.1,  # Low temperature for accuracy
            max_tokens=1000
        )
        
        api_elapsed = time.time() - api_start
        logger.info(f"[LLM API] Completed in {api_elapsed:.2f}s")
        
        return response.choices[0].message.content
    
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
        
        # Create messages
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"KYSYMYS: {query}\n\nKONTEKSTI:\n{context}"}
        ]
        
        # Stream response
        stream = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.1,
            max_tokens=1000,
            stream=True
        )
        
        for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
    
    def _build_context(self, chunks: List[Dict]) -> str:
        """
        Build context string from chunks with intelligent citation labels.
        
        - For statutes (with section numbers): Uses real § numbers like [§ 4]
        - For decisions/judgments (no sections): Uses [Lähde 1], [Lähde 2], etc.
        - For attachments: Uses [Liite: heading]
        - Always includes PDF URLs when available
        """
        context_parts = []
        source_counter = 1  # Counter for documents without section numbers
        
        for i, chunk in enumerate(chunks, 1):
            text = chunk.get('chunk_text', '')
            title = chunk.get('document_title', 'Unknown')
            uri = chunk.get('document_uri', '')
            doc_num = chunk.get('document_number')
            
            # Get the REAL section number from the chunk metadata
            section_number = chunk.get('section_number')
            
            # Build the citation reference label
            ref_label = self._get_reference_label(section_number, source_counter)
            if not section_number or not section_number.startswith('§'):
                source_counter += 1
            
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
