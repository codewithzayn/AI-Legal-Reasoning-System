"""
Document Chunker for Finnish Legal Documents
Splits documents by § sections while preserving structure
"""

import re
from typing import List, Dict
from dataclasses import dataclass


@dataclass
class Chunk:
    """Represents a chunk of legal text"""
    text: str
    chunk_index: int
    section_number: str
    metadata: Dict


class LegalDocumentChunker:
    """
    Chunks Finnish legal documents by § sections
    
    Features:
    - Splits by § (section) markers
    - Preserves section numbers for citations
    - Handles edge cases (no sections, very long sections)
    - Maintains document structure
    """
    
    def __init__(
        self, 
        max_chunk_size: int = 1000,
        min_chunk_size: int = 100,
        overlap: int = 50
    ):
        """
        Initialize chunker
        
        Args:
            max_chunk_size: Maximum words per chunk
            min_chunk_size: Minimum words per chunk (merge small sections)
            overlap: Words to overlap between chunks (for context)
        """
        self.max_chunk_size = max_chunk_size
        self.min_chunk_size = min_chunk_size
        self.overlap = overlap
        
        # Regex to find § sections
        # Matches: "§ 1", "§1", "§ 15 a", "1 §", etc.
        self.section_pattern = re.compile(
            r'^\s*§\s*(\d+(?:\s*[a-z])?)',
            re.MULTILINE
        )
    
    def chunk_document(
        self, 
        text: str, 
        document_uri: str,
        document_title: str,
        document_year: int
    ) -> List[Chunk]:
        """
        Split document into chunks by § sections
        
        Args:
            text: Full document text
            document_uri: Finlex URI for citations
            document_title: Document title
            document_year: Year of document
            
        Returns:
            List of Chunk objects
        """
        # Find all § section markers
        sections = self._split_by_sections(text)
        
        # If no sections found, split by size
        if len(sections) <= 1:
            return self._split_by_size(
                text, 
                document_uri, 
                document_title, 
                document_year
            )
        
        # Process sections into chunks
        chunks = []
        chunk_index = 0
        
        for section_num, section_text in sections:
            # Check if section is too large
            word_count = len(section_text.split())
            
            if word_count > self.max_chunk_size:
                # Split large section into sub-chunks
                sub_chunks = self._split_large_section(
                    section_text,
                    section_num,
                    chunk_index,
                    document_uri,
                    document_title,
                    document_year
                )
                chunks.extend(sub_chunks)
                chunk_index += len(sub_chunks)
            
            elif word_count < self.min_chunk_size and chunks:
                # Merge small section with previous chunk
                chunks[-1].text += f"\n\n{section_text}"
                chunks[-1].metadata['merged_sections'].append(section_num)
            
            else:
                # Normal-sized section
                chunks.append(Chunk(
                    text=section_text.strip(),
                    chunk_index=chunk_index,
                    section_number=section_num,
                    metadata={
                        'document_uri': document_uri,
                        'document_title': document_title,
                        'document_year': document_year,
                        'word_count': word_count,
                        'merged_sections': []
                    }
                ))
                chunk_index += 1
        
        return chunks
    
    def _split_by_sections(self, text: str) -> List[tuple]:
        """
        Split text by § section markers
        
        Returns:
            List of (section_number, section_text) tuples
        """
        sections = []
        matches = list(self.section_pattern.finditer(text))
        
        if not matches:
            return [("Preamble", text)]
        
        # Extract preamble (text before first section)
        first_match = matches[0]
        preamble = text[:first_match.start()].strip()
        if preamble:
            sections.append(("Preamble", preamble))
        
        # Extract each section
        for i, match in enumerate(matches):
            # Get section number
            section_num = match.group(1).strip()
            section_num = f"§ {section_num}"
            
            # Get section text (from this match to next match or end)
            start = match.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            section_text = text[start:end].strip()
            
            sections.append((section_num, section_text))
        
        return sections
    
    def _split_by_size(
        self, 
        text: str, 
        document_uri: str,
        document_title: str,
        document_year: int
    ) -> List[Chunk]:
        """
        Fallback: Split by size when no § sections found
        """
        words = text.split()
        chunks = []
        chunk_index = 0
        
        for i in range(0, len(words), self.max_chunk_size - self.overlap):
            chunk_words = words[i:i + self.max_chunk_size]
            chunk_text = ' '.join(chunk_words)
            
            chunks.append(Chunk(
                text=chunk_text,
                chunk_index=chunk_index,
                section_number=f"Part {chunk_index + 1}",
                metadata={
                    'document_uri': document_uri,
                    'document_title': document_title,
                    'document_year': document_year,
                    'word_count': len(chunk_words),
                    'merged_sections': [],
                    'split_method': 'size-based'
                }
            ))
            chunk_index += 1
        
        return chunks
    
    def _split_large_section(
        self,
        section_text: str,
        section_num: str,
        start_index: int,
        document_uri: str,
        document_title: str,
        document_year: int
    ) -> List[Chunk]:
        """
        Split a large § section into multiple chunks
        """
        words = section_text.split()
        chunks = []
        sub_index = 0
        
        for i in range(0, len(words), self.max_chunk_size - self.overlap):
            chunk_words = words[i:i + self.max_chunk_size]
            chunk_text = ' '.join(chunk_words)
            
            chunks.append(Chunk(
                text=chunk_text,
                chunk_index=start_index + sub_index,
                section_number=f"{section_num} (part {sub_index + 1})",
                metadata={
                    'document_uri': document_uri,
                    'document_title': document_title,
                    'document_year': document_year,
                    'word_count': len(chunk_words),
                    'merged_sections': [],
                    'split_method': 'large-section'
                }
            ))
            sub_index += 1
        
        return chunks
    
    def get_statistics(self, chunks: List[Chunk]) -> Dict:
        """Get chunking statistics"""
        return {
            'total_chunks': len(chunks),
            'avg_chunk_size': sum(c.metadata['word_count'] for c in chunks) / len(chunks) if chunks else 0,
            'min_chunk_size': min(c.metadata['word_count'] for c in chunks) if chunks else 0,
            'max_chunk_size': max(c.metadata['word_count'] for c in chunks) if chunks else 0,
            'sections_found': len([c for c in chunks if c.section_number.startswith('§')]),
            'merged_sections': sum(len(c.metadata['merged_sections']) for c in chunks)
        }

