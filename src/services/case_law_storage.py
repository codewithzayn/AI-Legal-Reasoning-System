"""
Case Law Storage Service
Stores case law documents and sections in Supabase with embeddings
"""

import os
from typing import List, Optional
from dataclasses import dataclass
from supabase import create_client, Client
from dotenv import load_dotenv

from src.config.logging_config import setup_logger
from src.services.case_law_scraper import CaseLawDocument
from src.services.embedder import DocumentEmbedder

load_dotenv()
logger = setup_logger(__name__)


@dataclass
class CaseLawSection:
    """Represents a section ready for embedding and storage"""
    case_law_id: str  # UUID from parent case_law record
    section_type: str
    section_number: int
    section_title: str
    content: str


class CaseLawStorage:
    """
    Store case law documents and sections in Supabase
    
    Features:
    - Inserts parent case into case_law table
    - Splits sections and inserts into case_law_sections table
    - Generates embeddings for each section
    - Handles duplicates via upsert
    """
    
    # Section types to store (map from CaseLawDocument attributes)
    SECTION_TYPES = [
        ("abstract", "Abstract / Summary"),
        ("lower_court", "Lower Court Decision"),
        ("court_of_appeal", "Court of Appeal"),
        ("appeal_to_supreme_court", "Appeal to Supreme Court"),
        ("reasoning", "Reasoning"),
        ("judgment", "Judgment / Verdict"),
    ]
    
    def __init__(self, url: Optional[str] = None, key: Optional[str] = None):
        """Initialize Supabase client and embedder"""
        self.url = url or os.getenv("SUPABASE_URL")
        self.key = key or os.getenv("SUPABASE_KEY")
        
        if not self.url or not self.key:
            raise ValueError("Supabase URL and KEY required. Set SUPABASE_URL and SUPABASE_KEY env vars.")
        
        self.client: Client = create_client(self.url, self.key)
        self.embedder = DocumentEmbedder()
    
    def store_case(self, doc: CaseLawDocument) -> Optional[str]:
        """
        Store a single case law document with all its sections
        
        Args:
            doc: CaseLawDocument from scraper
            
        Returns:
            UUID of inserted case_law record, or None if failed
        """
        try:
            # 1. Insert parent case_law record
            case_id = self._insert_case_metadata(doc)
            if not case_id:
                return None
            
            # 2. Extract and store sections with embeddings
            sections_stored = self._store_sections(case_id, doc)
            
            # 3. Store extracted references
            references_stored = self._store_references(case_id, doc)
            
            logger.info(f"Stored {doc.case_id}: {sections_stored} sections, {references_stored} references")
            return case_id
            
        except Exception as e:
            logger.error(f"Error storing case {doc.case_id}: {e}")
            return None
    
    def store_cases(self, docs: List[CaseLawDocument]) -> int:
        """
        Store multiple case law documents
        
        Args:
            docs: List of CaseLawDocument objects
            
        Returns:
            Number of cases successfully stored
        """
        stored_count = 0
        for doc in docs:
            result = self.store_case(doc)
            if result:
                stored_count += 1
        
        logger.info(f"Stored {stored_count}/{len(docs)} cases")
        return stored_count
    
    def _store_references(self, case_id: str, doc: CaseLawDocument) -> int:
        """Store extracted references in case_law_references table"""
        if not doc.references:
            return 0
        
        rows = []
        for ref in doc.references:
            rows.append({
                'source_case_id': case_id,
                'referenced_id': ref.ref_id,
                'reference_type': ref.ref_type
            })
        
        try:
            # Upsert (do nothing on conflict)
            response = self.client.table('case_law_references')\
                .upsert(rows, on_conflict='source_case_id,referenced_id')\
                .execute()
            
            return len(response.data) if response.data else 0
        except Exception as e:
            logger.error(f"Error storing references for {doc.case_id}: {e}")
            return 0
    
    def _insert_case_metadata(self, doc: CaseLawDocument) -> Optional[str]:
        """Insert case metadata into case_law table"""
        
        # Parse date from Finnish format (7.1.2026) to ISO format
        date_iso = None
        if doc.date:
            try:
                parts = doc.date.split('.')
                if len(parts) == 3:
                    date_iso = f"{parts[2]}-{parts[1].zfill(2)}-{parts[0].zfill(2)}"
            except Exception:
                pass
        
        row = {
            'case_id': doc.case_id,
            'court': doc.court,
            'year': doc.year,
            'case_number': doc.case_number,
            'decision_date': date_iso,
            'diary_number': doc.diary_number,
            'ecli': doc.ecli,
            'keywords': doc.keywords,
            'language': 'fin',
            'full_text': doc.full_text,
            'url': doc.url,
            'metadata': doc.metadata,
            'document_uri': doc.document_uri,
        }
        
        # Upsert to handle re-runs
        response = self.client.table('case_law')\
            .upsert(row, on_conflict='case_id')\
            .execute()
        
        if response.data:
            return response.data[0]['id']
        return None
    
    def _store_sections(self, case_law_id: str, doc: CaseLawDocument) -> int:
        """Extract sections, generate embeddings, and store"""
        
        sections = []
        section_number = 0
        
        for attr_name, section_title in self.SECTION_TYPES:
            content = getattr(doc, attr_name, "")
            if content and len(content) > 50:
                # 1. Primary Split: By Section
                
                # Check if we need further chunking (e.g. > 4000 chars)
                # Using 4000 to be safe for embeddings, though ADA-002 supports 8191 tokens (~32k chars)
                # But for retrieval quality, smaller chunks (1000-2000 chars) are often better.
                if len(content) > 4000:
                    chunks = self._chunk_text_recursive(content, max_size=2000, overlap=200)
                    for i, chunk in enumerate(chunks):
                        section_number += 1
                        sections.append(CaseLawSection(
                            case_law_id=case_law_id,
                            section_type=attr_name,
                            section_number=section_number,
                            section_title=f"{section_title} ({i+1}/{len(chunks)})",
                            content=chunk
                        ))
                else:
                    section_number += 1
                    sections.append(CaseLawSection(
                        case_law_id=case_law_id,
                        section_type=attr_name,
                        section_number=section_number,
                        section_title=section_title,
                        content=content
                    ))
        
        if not sections:
            return 0
        
        # Generate embeddings for all sections
        texts = [s.content for s in sections]
        embeddings = self._generate_embeddings(texts)
        
        # Prepare rows for insertion
        rows = []
        for section, embedding in zip(sections, embeddings):
            rows.append({
                'case_law_id': section.case_law_id,
                'section_type': section.section_type,
                'section_number': section.section_number,
                'section_title': section.section_title,
                'content': section.content,
                'embedding': embedding,
            })
        
        # Insert sections
        response = self.client.table('case_law_sections')\
            .insert(rows)\
            .execute()
        
        return len(response.data) if response.data else 0
    
    def _generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for a list of texts"""
        
        logger.info(f"Generating embeddings for {len(texts)} sections...")
        
        embeddings = []
        for text in texts:
            # Truncate very long texts (OpenAI has token limits)
            truncated = text[:8000] if len(text) > 8000 else text
            embedding = self.embedder.embed_query(truncated)
            embeddings.append(embedding)
        
        return embeddings
    
    def get_case_count(self, court: str = None, year: int = None) -> int:
        """Get count of stored cases with optional filters"""
        
        query = self.client.table('case_law').select('id', count='exact')
        
        if court:
            query = query.eq('court', court)
        if year:
            query = query.eq('year', year)
        
        response = query.execute()
        return response.count or 0
    
    def _chunk_text_recursive(self, text: str, max_size: int = 2000, overlap: int = 200) -> List[str]:
        """
        Recursively split text into smaller chunks
        Tries to split by:
        1. Double newlines (paragraphs)
        2. Single newlines
        3. Sentences/Spaces
        """
        if len(text) <= max_size:
            return [text]
            
        chunks = []
        start = 0
        text_len = len(text)
        
        while start < text_len:
            # End of this chunk
            end = start + max_size
            
            if end >= text_len:
                chunks.append(text[start:])
                break
            
            # Try to find a good break point
            # Look backwards from 'end'
            
            # 1. Paragraph break
            break_point = text.rfind('\n\n', start, end)
            if break_point == -1 or break_point < start + max_size // 2:
                # 2. Line break
                break_point = text.rfind('\n', start, end)
                
            if break_point == -1 or break_point < start + max_size // 2:
                # 3. Space
                break_point = text.rfind(' ', start, end)
                
            if break_point == -1:
                # Hard break
                break_point = end
            
            # Add chunk
            chunks.append(text[start:break_point].strip())
            
            # Move start for next chunk (apply overlap)
            start = break_point - overlap # Backtrack for overlap
            # Ensure we move forward at least a bit to avoid infinite loops
            if start <= break_point - max_size:
                 start = break_point
            
            # Clean up logic: if overlap pushes us back too far or not enough
            # Just ensure next chunk starts after the break, minus overlap
            start = max(0, break_point - overlap)
            
            # Safety checks against infinite loops
            if start >= break_point:
                 start = break_point + 1
                 
        return [c for c in chunks if c.strip()]
