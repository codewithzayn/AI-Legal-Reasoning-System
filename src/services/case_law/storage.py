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
from src.services.case_law.scraper import CaseLawDocument
from src.services.common.embedder import DocumentEmbedder

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
    Store case law documents and sections in Supabase (New Schema)
    """
    
    def __init__(self, url: Optional[str] = None, key: Optional[str] = None):
        """Initialize Supabase client and embedder"""
        self.url = url or os.getenv("SUPABASE_URL")
        self.key = key or os.getenv("SUPABASE_KEY")
        
        if not self.url or not self.key:
            raise ValueError("Supabase URL and KEY required. Set SUPABASE_URL and SUPABASE_KEY env vars.")
        
        self.client: Client = create_client(self.url, self.key)
        self.embedder = DocumentEmbedder()
    
    def store_case(self, doc: CaseLawDocument) -> Optional[str]:
        """Store a single case law document with all its sections"""
        try:
            # 1. Insert parent case_law record
            case_id = self._insert_case_metadata(doc)
            if not case_id:
                return None
            
            # 2. Extract and store sections with embeddings
            sections_stored = self._store_sections(case_id, doc)
            
            # 3. Store references (now populated by AI)
            references_stored = self._store_references(case_id, doc)
            
            logger.info(
                "%s | stored (%s sections, %s refs)",
                doc.case_id,
                sections_stored,
                references_stored,
            )
            return case_id
            
        except Exception as e:
            logger.error("%s | store error: %s", doc.case_id, e)
            return None
    
    def store_cases(self, docs: List[CaseLawDocument]) -> int:
        """Store multiple case law documents"""
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
                .upsert(rows, on_conflict='source_case_id,referenced_id,reference_type')\
                .execute()
            
            return len(response.data) if response.data else 0
        except Exception as e:
            logger.error(f"Error storing references for {doc.case_id}: {e}")
            return 0
            
    def _insert_case_metadata(self, doc: CaseLawDocument) -> Optional[str]:
        """Insert case metadata into case_law table (New Schema)"""
        
        row = {
            'case_id': doc.case_id,
            'court_type': doc.court_type,
            'court_code': doc.court_code,
            'decision_type': doc.decision_type,
            'case_year': doc.case_year,
            'decision_date': doc.decision_date, # Already ISO or None
            'diary_number': doc.diary_number,
            'ecli': doc.ecli,
            'primary_language': doc.primary_language,
            'available_languages': doc.available_languages,
            'full_text': doc.full_text,
            'url': doc.url,
            
            # Phase 3 Metadata Mapping
            'applicant': doc.applicant,
            'defendant': doc.defendant,
            'respondent': doc.respondent,
            
            'lower_court_name': doc.lower_court_name,
            'lower_court_date': doc.lower_court_date,
            'lower_court_number': doc.lower_court_number,
            'lower_court_decision': doc.lower_court_decision,
            
            'appeal_court_name': doc.appeal_court_name,
            'appeal_court_date': doc.appeal_court_date,
            'appeal_court_number': doc.appeal_court_number,
            
            'background_summary': doc.background_summary,
            'complaint': doc.complaint,
            'answer': doc.answer,
            'decision_outcome': doc.decision_outcome,
            'judgment': doc.judgment,
            
            'cited_laws': doc.cited_laws,
            'cited_cases': doc.cited_cases,
            'cited_government_proposals': doc.cited_government_proposals,
            'cited_eu_cases': doc.cited_eu_cases,
            'cited_regulations': doc.cited_regulations,
            'legal_domains': doc.legal_domains,
            'judges': doc.judges,
            
            # Extra metadata mapping
            'title': doc.title or f"{doc.court_code} {doc.case_year}:{doc.case_id.split(':')[-1] if ':' in doc.case_id else ''}",
            'is_precedent': doc.is_precedent,
            'volume': int(doc.volume) if doc.volume and str(doc.volume).isdigit() else None
        }
        
        # Upsert
        try:
            response = self.client.table('case_law')\
                .upsert(row, on_conflict='case_id')\
                .execute()
            
            if response.data:
                return response.data[0]['id']
            return None
        except Exception as e:
            logger.error(f"Error inserting metadata for {doc.case_id}: {e}")
            return None
    
    def _store_sections(self, case_law_id: str, doc: CaseLawDocument) -> int:
        """Extract sections, generate embeddings, and store in case_law_sections"""
        
        sections = []
        section_number = 0
        
        # Use AI-extracted sections when present and non-empty (filter empty content)
        ai_sections = getattr(doc, 'ai_sections', None) or []
        valid_ai = [
            s for s in ai_sections
            if isinstance(s, dict) and (s.get('content') or '').strip()
        ]
        if valid_ai:
            for i, section_data in enumerate(valid_ai):
                section_number += 1
                content = (section_data.get('content') or '').strip()
                metadata_header = f"[{doc.case_id}] {doc.title or ''}\nKeywords: {', '.join(doc.legal_domains or [])}\n\n"
                content_with_context = metadata_header + content
                sections.append({
                    'case_law_id': case_law_id,
                    'section_type': (section_data.get('type') or 'other').strip() or 'other',
                    'section_number': section_number,
                    'section_title': (section_data.get('title') or '').strip() or 'Section',
                    'content': content_with_context,
                    'embedding_priority': 'high'
                })
        if not sections:
            logger.warning("%s | fallback to chunked full text", doc.case_id)
            if doc.full_text:
                # Prepend metadata even for fallback
                metadata_header = f"[{doc.case_id}] {doc.title or ''}\nKeywords: {', '.join(doc.legal_domains or [])}\n\n"
                
                # Chunk the full text if it's too long
                chunk_size = 4000
                text = doc.full_text
                chunks = [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]
                
                for i, chunk_text in enumerate(chunks):
                    section_number += 1
                    content_with_context = metadata_header + chunk_text
                    
                    sections.append({
                        'case_law_id': case_law_id,
                        'section_type': 'reasoning',
                        'section_number': section_number,
                        'section_title': f"Full Text Part {i+1}",
                        'content': content_with_context,
                        'embedding_priority': 'medium'
                    })
        
        if not sections:
            return 0
        
        # Generate embeddings
        texts = [s['content'] for s in sections]
        embeddings = self._generate_embeddings(texts)
        
        # Attach embeddings
        for i, embedding in enumerate(embeddings):
            sections[i]['embedding'] = embedding
        
        # Insert
        try:
            # First, delete existing sections for this case to avoid duplicates
            self.client.table('case_law_sections')\
                .delete()\
                .eq('case_law_id', case_law_id)\
                .execute()
            
            # Then insert new sections
            response = self.client.table('case_law_sections')\
                .insert(sections)\
                .execute()
            
            return len(response.data) if response.data else 0
        except Exception as e:
            logger.error("%s | store sections error: %s", doc.case_id, e)
            return 0
    
    def _generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings via OpenAI"""
        if not texts:
            return []
            
        embeddings = []
        for text in texts:
            truncated = text[:8000] if len(text) > 8000 else text
            embedding = self.embedder.embed_query(truncated)
            embeddings.append(embedding)
        return embeddings
    
    def get_case_count(self, court_type: str = None, year: int = None) -> int:
        """Get count of stored cases"""
        query = self.client.table('case_law').select('id', count='exact')
        
        if court_type:
            query = query.eq('court_type', court_type)
        if year:
            query = query.eq('case_year', year)
        
        try:
            response = query.execute()
            return response.count or 0
        except Exception:
            return 0

