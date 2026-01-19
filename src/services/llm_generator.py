"""
LLM Response Generator
Generates legal responses with mandatory citations
"""

import os
import time
from typing import List, Dict
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()


SYSTEM_PROMPT = """You are a Finnish legal assistant. Answer questions based ONLY on the provided legal documents.

CRITICAL RULES:
1. Use ONLY the provided context
2. ALWAYS cite sources using [§X] format
3. If information is not in context, say: "Annettujen asiakirjojen perusteella en löydä tietoa tästä"
4. Never make assumptions or use external knowledge
5. Quote exact text when possible
6. **ALWAYS respond in Finnish language**

CITATION FORMAT:
- Use [§X] after each claim (e.g., "Työterveyshuolto on pakollista [§1]")
- Include document title and URI at the end
- Multiple sources: [§1, §2]

RESPONSE STRUCTURE:
1. Direct answer to question (in Finnish)
2. Supporting details with citations (in Finnish)
3. Sources at end in format:
   
LÄHTEET:
- [§X] Document title
  URI: https://...
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
        print(f"⏱️  [LLM API] Calling OpenAI...")
        api_start = time.time()
        
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.1,  # Low temperature for accuracy
            max_tokens=1000
        )
        
        api_elapsed = time.time() - api_start
        print(f"✅ [LLM API] Completed in {api_elapsed:.2f}s")
        
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
        """Build context string from chunks"""
        context_parts = []
        
        for i, chunk in enumerate(chunks, 1):
            section = chunk.get('section_number', 'N/A')
            text = chunk.get('chunk_text', '')
            title = chunk.get('document_title', 'Unknown')
            uri = chunk.get('document_uri', '')
            
            context_parts.append(
                f"[{section}] {text}\n"
                f"Lähde: {title}\n"
                f"URI: {uri}\n"
            )
        
        return "\n".join(context_parts)
